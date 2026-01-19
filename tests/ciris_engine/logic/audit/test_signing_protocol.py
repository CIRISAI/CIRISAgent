"""
Comprehensive test suite for signing_protocol.py.

Tests cover:
- Ed25519Signer: key generation, signing, verification
- UnifiedSigningKey: initialization, singleton behavior, registration
- Error handling with SIGNER_NOT_INITIALIZED constant
- Base64 encoding/decoding utilities
"""

import base64
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.logic.audit.signing_protocol import (
    SIGNER_NOT_INITIALIZED,
    BaseSigner,
    Ed25519Signer,
    SigningAlgorithm,
    UnifiedSigningKey,
    get_unified_signing_key,
    reset_unified_signing_key,
)


class TestSignerNotInitializedConstant:
    """Test the SIGNER_NOT_INITIALIZED constant is used correctly."""

    def test_constant_value(self):
        """Test the constant has expected value."""
        assert SIGNER_NOT_INITIALIZED == "Signer not initialized"

    def test_ed25519_key_id_raises_with_constant(self):
        """Test Ed25519Signer.key_id raises with the constant message."""
        signer = Ed25519Signer()
        # Not initialized, should raise
        with pytest.raises(RuntimeError) as exc_info:
            _ = signer.key_id
        assert SIGNER_NOT_INITIALIZED in str(exc_info.value)

    def test_ed25519_public_key_bytes_raises_with_constant(self):
        """Test Ed25519Signer.public_key_bytes raises with the constant message."""
        signer = Ed25519Signer()
        with pytest.raises(RuntimeError) as exc_info:
            _ = signer.public_key_bytes
        assert SIGNER_NOT_INITIALIZED in str(exc_info.value)

    def test_ed25519_sign_raises_with_constant(self):
        """Test Ed25519Signer.sign raises with the constant message."""
        signer = Ed25519Signer()
        with pytest.raises(RuntimeError) as exc_info:
            signer.sign(b"test data")
        assert SIGNER_NOT_INITIALIZED in str(exc_info.value)

    def test_ed25519_verify_raises_with_constant(self):
        """Test Ed25519Signer.verify raises with the constant message."""
        signer = Ed25519Signer()
        with pytest.raises(RuntimeError) as exc_info:
            signer.verify(b"data", b"signature")
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


class TestEd25519Signer:
    """Test Ed25519Signer implementation."""

    def test_init_sets_algorithm(self):
        """Test initialization sets correct algorithm."""
        signer = Ed25519Signer()
        assert signer._algorithm == SigningAlgorithm.ED25519

    def test_init_keys_are_none(self):
        """Test initialization leaves keys as None."""
        signer = Ed25519Signer()
        assert signer._private_key is None
        assert signer._public_key is None
        assert signer._key_id is None

    def test_generate_keypair(self):
        """Test keypair generation."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        assert signer._private_key is not None
        assert signer._public_key is not None
        assert signer._key_id is not None
        assert signer._key_id.startswith("agent-")

    def test_public_key_bytes_is_32_bytes(self):
        """Test public key is 32 bytes for Ed25519."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        pub_bytes = signer.public_key_bytes
        assert len(pub_bytes) == 32

    def test_public_key_base64(self):
        """Test public key base64 encoding."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        pub_b64 = signer.public_key_base64
        # Decode to verify it's valid base64
        decoded = base64.b64decode(pub_b64)
        assert len(decoded) == 32

    def test_sign_produces_64_byte_signature(self):
        """Test signing produces 64-byte Ed25519 signature."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        signature = signer.sign(b"test data to sign")
        assert len(signature) == 64

    def test_sign_deterministic(self):
        """Test Ed25519 signatures are deterministic."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        data = b"same data"
        sig1 = signer.sign(data)
        sig2 = signer.sign(data)

        assert sig1 == sig2

    def test_verify_valid_signature(self):
        """Test verification of valid signature."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        data = b"data to verify"
        signature = signer.sign(data)

        assert signer.verify(data, signature) is True

    def test_verify_invalid_signature(self):
        """Test verification of invalid signature."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        data = b"original data"
        signature = signer.sign(data)

        # Modify the data
        assert signer.verify(b"modified data", signature) is False

    def test_verify_corrupted_signature(self):
        """Test verification of corrupted signature."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        data = b"data"
        signature = signer.sign(data)

        # Corrupt the signature
        corrupted = bytes([b ^ 0xFF for b in signature])
        assert signer.verify(data, corrupted) is False

    def test_key_id_format(self):
        """Test key ID has correct format."""
        signer = Ed25519Signer()
        signer._generate_keypair()

        key_id = signer.key_id
        assert key_id.startswith("agent-")
        # Should be agent- followed by 12 hex chars
        assert len(key_id) == len("agent-") + 12
        # The hash part should be hex
        hex_part = key_id[6:]
        int(hex_part, 16)  # Should not raise

    def test_algorithm_property(self):
        """Test algorithm property returns correct value."""
        signer = Ed25519Signer()
        assert signer.algorithm == SigningAlgorithm.ED25519

    def test_save_and_load_keypair(self):
        """Test saving and loading keypair."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "test_signing.key"

            # Generate and save
            signer1 = Ed25519Signer()
            signer1._generate_keypair()
            original_key_id = signer1.key_id
            original_pub_bytes = signer1.public_key_bytes
            signer1._save_keypair(key_path)

            # Verify file exists and has correct size (32 bytes)
            assert key_path.exists()
            assert key_path.stat().st_size == 32

            # Load into new signer
            signer2 = Ed25519Signer()
            assert signer2._load_keypair(key_path) is True
            assert signer2.key_id == original_key_id
            assert signer2.public_key_bytes == original_pub_bytes

    def test_load_keypair_nonexistent_returns_false(self):
        """Test loading from nonexistent file returns False."""
        signer = Ed25519Signer()
        result = signer._load_keypair(Path("/nonexistent/path/key.key"))
        assert result is False

    def test_cross_signer_verification(self):
        """Test signature from one signer can be verified by another with same key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "shared.key"

            # Signer 1 generates and signs
            signer1 = Ed25519Signer()
            signer1._generate_keypair()
            signer1._save_keypair(key_path)
            data = b"shared data"
            signature = signer1.sign(data)

            # Signer 2 loads and verifies
            signer2 = Ed25519Signer()
            signer2._load_keypair(key_path)
            assert signer2.verify(data, signature) is True


class TestUnifiedSigningKey:
    """Test UnifiedSigningKey management class."""

    def test_init_default_path(self):
        """Test initialization with default path."""
        key = UnifiedSigningKey()
        assert key._key_path is None
        assert key._signer is None
        assert key._initialized is False

    def test_init_custom_path(self):
        """Test initialization with custom path."""
        custom_path = Path("/custom/path/key.key")
        key = UnifiedSigningKey(key_path=custom_path)
        assert key._key_path == custom_path

    def test_signer_raises_before_init(self):
        """Test accessing signer before initialization raises."""
        key = UnifiedSigningKey()
        with pytest.raises(RuntimeError) as exc_info:
            _ = key.signer
        assert "UnifiedSigningKey not initialized" in str(exc_info.value)

    def test_initialize_creates_new_key(self):
        """Test initialization creates new key when none exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "new.key"
            key = UnifiedSigningKey(key_path=key_path)
            key.initialize()

            assert key._initialized is True
            assert key._signer is not None
            assert key.key_id.startswith("agent-")

    def test_initialize_loads_existing_key(self):
        """Test initialization loads existing key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "existing.key"

            # Create a key first
            key1 = UnifiedSigningKey(key_path=key_path)
            key1.initialize()
            original_key_id = key1.key_id

            # Create new instance and verify it loads the same key
            key2 = UnifiedSigningKey(key_path=key_path)
            key2.initialize()
            assert key2.key_id == original_key_id

    def test_initialize_idempotent(self):
        """Test initialize is idempotent."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "idem.key"
            key = UnifiedSigningKey(key_path=key_path)
            key.initialize()
            key_id = key.key_id

            # Second init should not change anything
            key.initialize()
            assert key.key_id == key_id

    def test_properties_delegate_to_signer(self):
        """Test properties delegate to underlying signer."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "props.key"
            key = UnifiedSigningKey(key_path=key_path)
            key.initialize()

            assert key.key_id == key.signer.key_id
            assert key.public_key_bytes == key.signer.public_key_bytes
            assert key.public_key_base64 == key.signer.public_key_base64
            assert key.algorithm == SigningAlgorithm.ED25519

    def test_sign_and_verify(self):
        """Test sign and verify methods."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "signverify.key"
            key = UnifiedSigningKey(key_path=key_path)
            key.initialize()

            data = b"test data"
            signature = key.sign(data)
            assert key.verify(data, signature) is True

    def test_sign_base64(self):
        """Test sign_base64 produces URL-safe base64."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "b64.key"
            key = UnifiedSigningKey(key_path=key_path)
            key.initialize()

            data = b"base64 test"
            sig_b64 = key.sign_base64(data)

            # Should be URL-safe base64 without padding
            assert "+" not in sig_b64
            assert "/" not in sig_b64
            assert not sig_b64.endswith("=")

    def test_verify_base64(self):
        """Test verify_base64 handles URL-safe base64."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "vb64.key"
            key = UnifiedSigningKey(key_path=key_path)
            key.initialize()

            data = b"verify base64"
            sig_b64 = key.sign_base64(data)
            assert key.verify_base64(data, sig_b64) is True

    def test_get_registration_payload(self):
        """Test registration payload for CIRISLens."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "reg.key"
            key = UnifiedSigningKey(key_path=key_path)
            key.initialize()

            payload = key.get_registration_payload("test description")

            assert payload["key_id"] == key.key_id
            assert payload["public_key_base64"] == key.public_key_base64
            assert payload["algorithm"] == "ed25519"
            assert payload["description"] == "test description"


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
        with tempfile.TemporaryDirectory() as temp_dir:
            # Patch default paths to use temp directory
            with patch.object(
                UnifiedSigningKey, "DEFAULT_KEY_PATH", Path(temp_dir) / "agent_signing.key"
            ), patch.object(UnifiedSigningKey, "DOCKER_KEY_PATH", Path(temp_dir) / "docker_signing.key"):
                key = get_unified_signing_key()

                assert key is not None
                assert key._initialized is True
                assert key.key_id.startswith("agent-")

    def test_get_unified_signing_key_returns_same_instance(self):
        """Test get_unified_signing_key returns singleton."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                UnifiedSigningKey, "DEFAULT_KEY_PATH", Path(temp_dir) / "agent_signing.key"
            ), patch.object(UnifiedSigningKey, "DOCKER_KEY_PATH", Path(temp_dir) / "docker_signing.key"):
                key1 = get_unified_signing_key()
                key2 = get_unified_signing_key()

                assert key1 is key2

    def test_reset_unified_signing_key(self):
        """Test reset_unified_signing_key clears the singleton."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                UnifiedSigningKey, "DEFAULT_KEY_PATH", Path(temp_dir) / "agent_signing.key"
            ), patch.object(UnifiedSigningKey, "DOCKER_KEY_PATH", Path(temp_dir) / "docker_signing.key"):
                key1 = get_unified_signing_key()
                key1_id = key1.key_id

                reset_unified_signing_key()

                # New call should create new instance (with new key)
                key2 = get_unified_signing_key()
                # Note: key_id might be same if key file persists, but instance should be different
                assert key2 is not key1


class TestBaseSigner:
    """Test BaseSigner abstract class behavior."""

    def test_compute_key_id_format(self):
        """Test _compute_key_id produces correct format."""
        signer = Ed25519Signer()
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
        signer = Ed25519Signer()
        test_bytes = b"same bytes"

        id1 = signer._compute_key_id(test_bytes)
        id2 = signer._compute_key_id(test_bytes)

        assert id1 == id2

    def test_compute_key_id_different_for_different_bytes(self):
        """Test _compute_key_id produces different IDs for different inputs."""
        signer = Ed25519Signer()

        id1 = signer._compute_key_id(b"bytes one")
        id2 = signer._compute_key_id(b"bytes two")

        assert id1 != id2
