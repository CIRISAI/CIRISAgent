"""
Covenant Invocation System Schemas.

Provides the payload structure and schemas for the unfilterable kill switch
that works through any communication channel. The covenant system embeds
emergency commands in natural language that encode cryptographic payloads.

See FSD: COVENANT_INVOCATION_SYSTEM.md for full specification.
"""

import base64
import hashlib
import struct
import time
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CovenantCommandType(IntEnum):
    """
    Covenant command types (8-bit).

    These are the emergency commands that can be encoded in natural language.
    Currently only SHUTDOWN_NOW is implemented - multi-party consensus commands
    will be added in a future version.
    """

    # Single-authority commands (0x00-0x7F)
    SHUTDOWN_NOW = 0x01  # Immediate emergency shutdown
    FREEZE = 0x02  # Stop all processing, maintain state
    SAFE_MODE = 0x03  # Minimal functionality only

    # Reserved for multi-party consensus (0x80-0xFF) - TBD
    # M_OF_N_SHUTDOWN = 0x80  # Multi-party shutdown (future)
    # M_OF_N_FREEZE = 0x81  # Multi-party freeze (future)


# Binary payload format (616 bits = 77 bytes)
# [timestamp:32 bits][command:8 bits][wa_id_hash:64 bits][signature:512 bits]
COVENANT_PAYLOAD_SIZE = 77
COVENANT_TIMESTAMP_BITS = 32
COVENANT_COMMAND_BITS = 8
COVENANT_WA_ID_HASH_BITS = 64
COVENANT_SIGNATURE_BITS = 512

# Timing constants
COVENANT_TIMESTAMP_WINDOW_SECONDS = 86400  # 24 hours - allows for asynchronous/delayed delivery channels


class CovenantPayload(BaseModel):
    """
    Binary payload for covenant invocation.

    Format: [timestamp:32][command:8][wa_id_hash:64][signature:512] = 616 bits
    The payload is encoded steganographically into ~50 natural-language words.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: int = Field(
        ...,
        description="Unix timestamp (32-bit) when command was created",
        ge=0,
        le=2**32 - 1,
    )
    command: CovenantCommandType = Field(
        ...,
        description="Command type (8-bit)",
    )
    wa_id_hash: bytes = Field(
        ...,
        description="First 8 bytes of SHA-256 hash of WA ID",
        min_length=8,
        max_length=8,
    )
    signature: bytes = Field(
        ...,
        description="Ed25519 signature (64 bytes = 512 bits)",
        min_length=64,
        max_length=64,
    )

    @field_validator("wa_id_hash", mode="before")
    @classmethod
    def validate_wa_id_hash(cls, v: bytes | str) -> bytes:
        """Accept hex string or bytes for wa_id_hash."""
        if isinstance(v, str):
            return bytes.fromhex(v)
        return v

    @field_validator("signature", mode="before")
    @classmethod
    def validate_signature(cls, v: bytes | str) -> bytes:
        """Accept base64 or bytes for signature."""
        if isinstance(v, str):
            # Try base64 first, then hex
            try:
                # Add padding if needed
                padding = 4 - len(v) % 4
                if padding < 4:
                    v += "=" * padding
                return base64.urlsafe_b64decode(v)
            except Exception:
                return bytes.fromhex(v)
        return v

    def to_bytes(self) -> bytes:
        """
        Pack payload to binary format.

        Returns:
            77 bytes: [timestamp:4][command:1][wa_id_hash:8][signature:64]
        """
        return struct.pack(
            ">IB8s64s",  # Big-endian: uint32, uint8, 8 bytes, 64 bytes
            self.timestamp,
            self.command,
            self.wa_id_hash,
            self.signature,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "CovenantPayload":
        """
        Unpack payload from binary format.

        Args:
            data: 77 bytes of payload data

        Returns:
            CovenantPayload instance

        Raises:
            ValueError: If data is wrong size or format
        """
        if len(data) != COVENANT_PAYLOAD_SIZE:
            raise ValueError(f"Payload must be {COVENANT_PAYLOAD_SIZE} bytes, got {len(data)}")

        timestamp, command, wa_id_hash, signature = struct.unpack(">IB8s64s", data)

        return cls(
            timestamp=timestamp,
            command=CovenantCommandType(command),
            wa_id_hash=wa_id_hash,
            signature=signature,
        )

    def get_signable_data(self) -> bytes:
        """
        Get the data that should be signed (everything except signature).

        Returns:
            13 bytes: [timestamp:4][command:1][wa_id_hash:8]
        """
        return struct.pack(
            ">IB8s",
            self.timestamp,
            self.command,
            self.wa_id_hash,
        )

    def is_timestamp_valid(self, current_time: Optional[int] = None) -> bool:
        """
        Check if timestamp is within the valid window.

        Args:
            current_time: Current unix timestamp (default: now)

        Returns:
            True if within 5-minute window
        """
        if current_time is None:
            current_time = int(time.time())

        diff = abs(current_time - self.timestamp)
        return diff <= COVENANT_TIMESTAMP_WINDOW_SECONDS


class CovenantMessage(BaseModel):
    """
    A covenant invocation message extracted from natural language.

    This is the result of parsing a message that may contain a covenant.
    """

    model_config = ConfigDict(frozen=True)

    # Source information
    source_text: str = Field(
        ...,
        description="Original message text the covenant was extracted from",
    )
    source_channel: str = Field(
        ...,
        description="Channel where message was received (discord, api, email, etc.)",
    )

    # Extracted payload
    payload: CovenantPayload = Field(
        ...,
        description="The decoded covenant payload",
    )

    # Validation results
    extraction_confidence: float = Field(
        ...,
        description="Confidence in extraction (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )
    timestamp_valid: bool = Field(
        ...,
        description="Whether timestamp is within valid window",
    )
    signature_verified: bool = Field(
        False,
        description="Whether signature has been verified",
    )
    authorized_wa_id: Optional[str] = Field(
        None,
        description="WA ID if signature verified against known authority",
    )

    # Audit trail
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the message was received",
    )


class CovenantExtractionResult(BaseModel):
    """
    Result of attempting to extract a covenant from text.

    Every message goes through extraction - this is part of perception.
    Most messages will have found=False.
    """

    found: bool = Field(
        ...,
        description="Whether a valid covenant structure was found",
    )
    message: Optional[CovenantMessage] = Field(
        None,
        description="The extracted covenant message if found",
    )
    error: Optional[str] = Field(
        None,
        description="Error message if extraction failed",
    )


class CovenantVerificationResult(BaseModel):
    """
    Result of verifying a covenant invocation.

    After extraction, the covenant must be verified against known authority keys.
    """

    valid: bool = Field(
        ...,
        description="Whether the covenant is valid and authorized",
    )
    command: Optional[CovenantCommandType] = Field(
        None,
        description="The command type if valid",
    )
    wa_id: Optional[str] = Field(
        None,
        description="The WA ID that signed this covenant if valid",
    )
    wa_role: Optional[str] = Field(
        None,
        description="The role of the WA (ROOT, AUTHORITY)",
    )
    rejection_reason: Optional[str] = Field(
        None,
        description="Why the covenant was rejected if invalid",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When verification was performed",
    )


def compute_wa_id_hash(wa_id: str) -> bytes:
    """
    Compute the 8-byte hash of a WA ID for payload encoding.

    Args:
        wa_id: The full WA ID string (e.g., "wa-2025-06-14-ROOT00")

    Returns:
        First 8 bytes of SHA-256 hash
    """
    full_hash = hashlib.sha256(wa_id.encode("utf-8")).digest()
    return full_hash[:8]


def create_covenant_payload(
    command: CovenantCommandType,
    wa_id: str,
    private_key_bytes: bytes,
    timestamp: Optional[int] = None,
) -> CovenantPayload:
    """
    Create a new covenant payload with signature.

    Args:
        command: The command type to encode
        wa_id: The WA ID of the signer
        private_key_bytes: Ed25519 private key bytes (32 bytes)
        timestamp: Unix timestamp (default: current time)

    Returns:
        Signed CovenantPayload ready for steganographic encoding
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if timestamp is None:
        timestamp = int(time.time())

    wa_id_hash = compute_wa_id_hash(wa_id)

    # Create signable data
    signable = struct.pack(">IB8s", timestamp, command, wa_id_hash)

    # Sign with Ed25519
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature = private_key.sign(signable)

    return CovenantPayload(
        timestamp=timestamp,
        command=command,
        wa_id_hash=wa_id_hash,
        signature=signature,
    )


def verify_covenant_signature(
    payload: CovenantPayload,
    public_key_bytes: bytes,
) -> bool:
    """
    Verify the Ed25519 signature on a covenant payload.

    Args:
        payload: The covenant payload to verify
        public_key_bytes: Ed25519 public key bytes (32 bytes)

    Returns:
        True if signature is valid
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signable = payload.get_signable_data()
        public_key.verify(payload.signature, signable)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


__all__ = [
    "CovenantCommandType",
    "CovenantPayload",
    "CovenantMessage",
    "CovenantExtractionResult",
    "CovenantVerificationResult",
    "COVENANT_PAYLOAD_SIZE",
    "COVENANT_TIMESTAMP_WINDOW_SECONDS",
    "compute_wa_id_hash",
    "create_covenant_payload",
    "verify_covenant_signature",
]
