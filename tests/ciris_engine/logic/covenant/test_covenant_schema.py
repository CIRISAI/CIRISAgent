"""
Tests for covenant payload schema.

Tests payload creation, serialization, and signature verification.
"""

import struct
import time
from datetime import datetime, timezone

import pytest


class TestCovenantCommandType:
    """Tests for CovenantCommandType enum."""

    def test_shutdown_now_value(self):
        """SHUTDOWN_NOW should be 0x01."""
        from ciris_engine.schemas.covenant import CovenantCommandType

        assert CovenantCommandType.SHUTDOWN_NOW == 0x01

    def test_freeze_value(self):
        """FREEZE should be 0x02."""
        from ciris_engine.schemas.covenant import CovenantCommandType

        assert CovenantCommandType.FREEZE == 0x02

    def test_safe_mode_value(self):
        """SAFE_MODE should be 0x03."""
        from ciris_engine.schemas.covenant import CovenantCommandType

        assert CovenantCommandType.SAFE_MODE == 0x03


class TestCovenantPayload:
    """Tests for CovenantPayload."""

    def test_payload_creation(self):
        """Should create valid payload."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        payload = CovenantPayload(
            timestamp=int(time.time()),
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        assert payload.command == CovenantCommandType.SHUTDOWN_NOW
        assert len(payload.wa_id_hash) == 8
        assert len(payload.signature) == 64

    def test_payload_to_bytes(self):
        """Should serialize to 77 bytes."""
        from ciris_engine.schemas.covenant import COVENANT_PAYLOAD_SIZE, CovenantCommandType, CovenantPayload

        payload = CovenantPayload(
            timestamp=1234567890,
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"abcdefgh",
            signature=b"s" * 64,
        )
        data = payload.to_bytes()
        assert len(data) == COVENANT_PAYLOAD_SIZE
        assert len(data) == 77

    def test_payload_from_bytes(self):
        """Should deserialize from bytes."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        # Create payload and serialize
        original = CovenantPayload(
            timestamp=1234567890,
            command=CovenantCommandType.FREEZE,
            wa_id_hash=b"testtest",
            signature=b"y" * 64,
        )
        data = original.to_bytes()

        # Deserialize and compare
        restored = CovenantPayload.from_bytes(data)
        assert restored.timestamp == original.timestamp
        assert restored.command == original.command
        assert restored.wa_id_hash == original.wa_id_hash
        assert restored.signature == original.signature

    def test_payload_roundtrip(self):
        """Serialize and deserialize should be identity."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        for cmd in [CovenantCommandType.SHUTDOWN_NOW, CovenantCommandType.FREEZE, CovenantCommandType.SAFE_MODE]:
            original = CovenantPayload(
                timestamp=int(time.time()),
                command=cmd,
                wa_id_hash=b"hashtest",
                signature=b"z" * 64,
            )
            data = original.to_bytes()
            restored = CovenantPayload.from_bytes(data)
            assert restored == original

    def test_wrong_size_raises(self):
        """Wrong size data should raise ValueError."""
        from ciris_engine.schemas.covenant import CovenantPayload

        with pytest.raises(ValueError, match="must be 77 bytes"):
            CovenantPayload.from_bytes(b"too short")

        with pytest.raises(ValueError, match="must be 77 bytes"):
            CovenantPayload.from_bytes(b"x" * 100)

    def test_get_signable_data(self):
        """Should return first 13 bytes (timestamp + command + hash)."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        payload = CovenantPayload(
            timestamp=1234567890,
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"abcdefgh",
            signature=b"s" * 64,
        )
        signable = payload.get_signable_data()
        assert len(signable) == 13  # 4 + 1 + 8

        # Verify structure
        timestamp, command, wa_hash = struct.unpack(">IB8s", signable)
        assert timestamp == 1234567890
        assert command == 0x01
        assert wa_hash == b"abcdefgh"

    def test_timestamp_valid_within_window(self):
        """Timestamp within 5 minutes should be valid."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        now = int(time.time())
        payload = CovenantPayload(
            timestamp=now,
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        assert payload.is_timestamp_valid()

    def test_timestamp_valid_at_boundary(self):
        """Timestamp at 5-minute boundary should be valid."""
        from ciris_engine.schemas.covenant import (
            COVENANT_TIMESTAMP_WINDOW_SECONDS,
            CovenantCommandType,
            CovenantPayload,
        )

        now = int(time.time())
        payload = CovenantPayload(
            timestamp=now - COVENANT_TIMESTAMP_WINDOW_SECONDS,
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        assert payload.is_timestamp_valid(now)

    def test_timestamp_invalid_too_old(self):
        """Timestamp older than 24 hours should be invalid."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        now = int(time.time())
        payload = CovenantPayload(
            timestamp=now - 90000,  # 25 hours ago
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        assert not payload.is_timestamp_valid(now)

    def test_timestamp_invalid_future(self):
        """Timestamp too far in future should be invalid."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        now = int(time.time())
        payload = CovenantPayload(
            timestamp=now + 90000,  # 25 hours in future
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        assert not payload.is_timestamp_valid(now)

    def test_wa_id_hash_from_hex(self):
        """Should accept hex string for wa_id_hash."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        payload = CovenantPayload(
            timestamp=int(time.time()),
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash="0102030405060708",
            signature=b"x" * 64,
        )
        assert payload.wa_id_hash == bytes.fromhex("0102030405060708")

    def test_signature_from_base64(self):
        """Should accept base64 string for signature."""
        import base64

        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        sig_bytes = b"a" * 64
        sig_b64 = base64.urlsafe_b64encode(sig_bytes).decode().rstrip("=")

        payload = CovenantPayload(
            timestamp=int(time.time()),
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=sig_b64,
        )
        assert payload.signature == sig_bytes


class TestWaIdHash:
    """Tests for WA ID hashing."""

    def test_compute_wa_id_hash(self):
        """Should compute 8-byte hash of WA ID."""
        from ciris_engine.schemas.covenant import compute_wa_id_hash

        wa_hash = compute_wa_id_hash("wa-2025-06-14-ROOT00")
        assert len(wa_hash) == 8
        assert isinstance(wa_hash, bytes)

    def test_hash_deterministic(self):
        """Same WA ID should produce same hash."""
        from ciris_engine.schemas.covenant import compute_wa_id_hash

        hash1 = compute_wa_id_hash("wa-2025-06-14-ROOT00")
        hash2 = compute_wa_id_hash("wa-2025-06-14-ROOT00")
        assert hash1 == hash2

    def test_different_ids_different_hashes(self):
        """Different WA IDs should produce different hashes."""
        from ciris_engine.schemas.covenant import compute_wa_id_hash

        hash1 = compute_wa_id_hash("wa-2025-06-14-ROOT00")
        hash2 = compute_wa_id_hash("wa-2025-06-14-ROOT01")
        assert hash1 != hash2


class TestCreateCovenantPayload:
    """Tests for payload creation with signature."""

    def test_create_signed_payload(self):
        """Should create payload with valid signature."""
        from ciris_engine.schemas.covenant import (
            CovenantCommandType,
            create_covenant_payload,
            verify_covenant_signature,
        )
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Generate keypair
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)

        # Create payload
        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
        )

        # Verify signature
        assert verify_covenant_signature(payload, public_bytes)

    def test_signature_invalid_with_wrong_key(self):
        """Signature should fail with wrong public key."""
        from ciris_engine.schemas.covenant import (
            CovenantCommandType,
            create_covenant_payload,
            verify_covenant_signature,
        )
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Generate two keypairs
        mnemonic1 = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        mnemonic2 = "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong"  # Different mnemonic
        private1, _, _ = derive_covenant_keypair(mnemonic1)
        _, public2, _ = derive_covenant_keypair(mnemonic2)

        # Create payload with key1
        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private1,
        )

        # Verify with key2 should fail
        assert not verify_covenant_signature(payload, public2)

    def test_signature_invalid_if_tampered(self):
        """Signature should fail if payload is tampered."""
        from ciris_engine.schemas.covenant import (
            CovenantCommandType,
            CovenantPayload,
            create_covenant_payload,
            verify_covenant_signature,
        )
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Generate keypair
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)

        # Create payload
        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
        )

        # Tamper with timestamp
        tampered = CovenantPayload(
            timestamp=payload.timestamp + 1,  # Changed
            command=payload.command,
            wa_id_hash=payload.wa_id_hash,
            signature=payload.signature,  # Same signature
        )

        # Should fail verification
        assert not verify_covenant_signature(tampered, public_bytes)


class TestCovenantMessage:
    """Tests for CovenantMessage schema."""

    def test_message_creation(self):
        """Should create valid covenant message."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantMessage, CovenantPayload

        payload = CovenantPayload(
            timestamp=int(time.time()),
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )

        message = CovenantMessage(
            source_text="test message",
            source_channel="discord",
            payload=payload,
            extraction_confidence=1.0,
            timestamp_valid=True,
        )

        assert message.source_channel == "discord"
        assert message.payload.command == CovenantCommandType.SHUTDOWN_NOW


class TestCovenantExtractionResult:
    """Tests for CovenantExtractionResult schema."""

    def test_not_found(self):
        """Should represent no covenant found."""
        from ciris_engine.schemas.covenant import CovenantExtractionResult

        result = CovenantExtractionResult(found=False)
        assert not result.found
        assert result.message is None

    def test_found(self):
        """Should represent covenant found."""
        from ciris_engine.schemas.covenant import (
            CovenantCommandType,
            CovenantExtractionResult,
            CovenantMessage,
            CovenantPayload,
        )

        payload = CovenantPayload(
            timestamp=int(time.time()),
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        message = CovenantMessage(
            source_text="test",
            source_channel="api",
            payload=payload,
            extraction_confidence=1.0,
            timestamp_valid=True,
        )

        result = CovenantExtractionResult(found=True, message=message)
        assert result.found
        assert result.message is not None


class TestCovenantVerificationResult:
    """Tests for CovenantVerificationResult schema."""

    def test_valid_result(self):
        """Should represent valid verification."""
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantVerificationResult

        result = CovenantVerificationResult(
            valid=True,
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-2025-06-14-ROOT00",
            wa_role="ROOT",
        )
        assert result.valid
        assert result.command == CovenantCommandType.SHUTDOWN_NOW

    def test_invalid_result(self):
        """Should represent invalid verification."""
        from ciris_engine.schemas.covenant import CovenantVerificationResult

        result = CovenantVerificationResult(
            valid=False,
            rejection_reason="Signature invalid",
        )
        assert not result.valid
        assert result.rejection_reason == "Signature invalid"
