"""
Emergency shutdown resource for CIRIS v1 API (Pre-Beta).

This resource handles the critical emergency shutdown endpoint that bypasses
normal authentication to ensure remote ROOT/AUTHORITY can always execute
emergency shutdown even if the main API auth is compromised or unavailable.
"""

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import BaseModel, Field

from ..exceptions import CIRISError
from ..transport import Transport

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    Ed25519PrivateKey = type(None)  # type: ignore[misc,assignment]  # Define for type annotations when crypto unavailable


class EmergencyCommandType(str, Enum):
    """Types of emergency commands."""

    SHUTDOWN_NOW = "SHUTDOWN_NOW"
    FREEZE = "FREEZE"
    SAFE_MODE = "SAFE_MODE"


class WASignedCommand(BaseModel):
    """A command signed by a Wise Authority - matches server schema."""

    command_id: str = Field(..., description="Unique command identifier")
    command_type: EmergencyCommandType = Field(..., description="Type of emergency command")

    # WA authority
    wa_id: str = Field(..., description="ID of issuing WA")
    wa_public_key: str = Field(..., description="Public key of issuing WA")

    # Command details
    issued_at: datetime = Field(..., description="When command was issued")
    expires_at: Optional[datetime] = Field(None, description="Command expiration")
    reason: str = Field(..., description="Reason for emergency command")

    # Targeting
    target_agent_id: Optional[str] = Field(None, description="Specific agent or None for all")
    target_tree_path: Optional[List[str]] = Field(None, description="WA tree path for targeting")

    # Signature
    signature: str = Field(..., description="Ed25519 signature of command data")

    # Chain of authority
    parent_command_id: Optional[str] = Field(None, description="Parent command if relayed")
    relay_chain: List[str] = Field(default_factory=list, description="WA IDs in relay chain")


class EmergencyShutdownResponse(BaseModel):
    """Response from emergency shutdown."""

    success: bool = Field(..., description="Whether shutdown was initiated")
    message: str = Field(..., description="Status message")


class EmergencyResource:
    """
    Emergency operations for v1 API (Pre-Beta).

    **WARNING**: This SDK is for the v1 API which is in pre-beta stage.

    **CRITICAL**: The emergency shutdown endpoint bypasses normal authentication
    to ensure remote ROOT/AUTHORITY can always execute emergency shutdown even if
    the main API auth is compromised or unavailable.

    Security features:
    - Requires Ed25519 cryptographically signed command
    - Signature must be from ROOT or AUTHORITY key
    - Timestamp must be within 5-minute window
    - Executes immediate shutdown without negotiation
    - Separate from /v1/system/shutdown to avoid auth dependencies
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        if not CRYPTO_AVAILABLE:
            raise CIRISError(
                "cryptography package required for emergency shutdown. Install with: pip install cryptography"
            )

    async def shutdown(
        self,
        reason: str,
        private_key: "Ed25519PrivateKey",
        wa_id: str,
        wa_public_key: str,
        target_agent_id: Optional[str] = None,
        expires_minutes: int = 5,
    ) -> EmergencyShutdownResponse:
        """
        Execute emergency shutdown with Ed25519 signed command.

        This endpoint bypasses normal authentication and requires a
        cryptographically signed command. The signing key must be from
        a ROOT or AUTHORITY Wise Authority.

        Args:
            reason: Reason for emergency shutdown
            private_key: Ed25519 private key for signing
            wa_id: ID of the Wise Authority issuing command
            wa_public_key: Base64-encoded public key of the WA
            target_agent_id: Optional specific agent to shutdown
            expires_minutes: Command expiration in minutes (default 5)

        Returns:
            EmergencyShutdownResponse indicating if shutdown was initiated

        Raises:
            CIRISError: If crypto not available or request fails

        Example:
            # Generate or load Ed25519 key pair
            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key()
            public_key_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )

            response = await client.emergency.shutdown(
                reason="Critical security incident",
                private_key=private_key,
                wa_id="root_authority_001",
                wa_public_key=base64.b64encode(public_key_bytes).decode()
            )
        """
        # Create the command
        now = datetime.now(timezone.utc)
        command = WASignedCommand(
            command_id=str(uuid.uuid4()),
            command_type=EmergencyCommandType.SHUTDOWN_NOW,
            wa_id=wa_id,
            wa_public_key=wa_public_key,
            issued_at=now,
            expires_at=now + timedelta(minutes=expires_minutes),
            reason=reason,
            target_agent_id=target_agent_id,
            signature="",  # Will be filled after signing
        )

        # Sign the command
        command.signature = self._sign_command(command, private_key)

        # Send to emergency endpoint (note: NOT under /v1/)
        result = await self._transport.request("POST", "/emergency/shutdown", json=command.model_dump())

        assert result is not None, "Emergency shutdown request returned no data"
        return EmergencyShutdownResponse(**result)

    def _sign_command(self, command: WASignedCommand, private_key: Ed25519PrivateKey) -> str:
        """
        Create Ed25519 signature of the command data.

        Args:
            command: The command to sign
            private_key: Ed25519 private key

        Returns:
            Hex-encoded signature
        """
        # Build the message that will be signed (must match server verification)
        # Use pipe-delimited format matching server's _verify_wa_signature method
        parts = [
            f"command_id:{command.command_id}",
            f"command_type:{command.command_type}",
            f"wa_id:{command.wa_id}",
            f"issued_at:{command.issued_at.isoformat()}",
            f"reason:{command.reason}",
        ]

        # Only add target_agent_id if it exists (matching server logic)
        if command.target_agent_id:
            parts.append(f"target_agent_id:{command.target_agent_id}")

        # Create pipe-delimited message
        message = "|".join(parts).encode("utf-8")

        # Sign with Ed25519
        signature_bytes = private_key.sign(message)

        # Return hex-encoded signature to match server expectation
        return signature_bytes.hex()

    def verify_signature(self, command: WASignedCommand, public_key_bytes: bytes) -> bool:
        """
        Verify an Ed25519 signature matches the command.

        This is useful for testing or verification purposes.

        Args:
            command: The command with signature
            public_key_bytes: Raw bytes of Ed25519 public key

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            # Create public key
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

            # Build message (same as _sign_command)
            parts = [
                f"command_id:{command.command_id}",
                f"command_type:{command.command_type}",
                f"wa_id:{command.wa_id}",
                f"issued_at:{command.issued_at.isoformat()}",
                f"reason:{command.reason}",
            ]

            # Only add target_agent_id if it exists
            if command.target_agent_id:
                parts.append(f"target_agent_id:{command.target_agent_id}")

            message = "|".join(parts).encode("utf-8")

            # Verify signature (now hex-encoded)
            signature_bytes = bytes.fromhex(command.signature)
            public_key.verify(signature_bytes, message)
            return True

        except (InvalidSignature, ValueError):
            return False
        except Exception:
            return False
