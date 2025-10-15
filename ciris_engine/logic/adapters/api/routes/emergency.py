"""
Emergency Shutdown endpoint for CIRIS API.

Provides cryptographically signed emergency shutdown functionality
that operates outside normal authentication (signature IS the auth).
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from ciris_engine.schemas.types import JSONDict

try:
    # Try to import Ed25519 verification
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logging.warning("Ed25519 crypto not available - emergency shutdown will be disabled")

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.shutdown import EmergencyCommandType, EmergencyShutdownStatus, WASignedCommand

from ..constants import ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE

logger = logging.getLogger(__name__)

# Create router without prefix - this is mounted at root level
router = APIRouter(tags=["emergency"])

# Hardcoded root WA authority public keys for emergency shutdown
# In production, these would be loaded from secure configuration
ROOT_WA_AUTHORITY_KEYS = [
    # Root WA key from ~/.ciris/wa_keys/root_wa_metadata.json
    "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk",
    # Example Ed25519 public key (base64 encoded)
    # "MCowBQYDK2VwAyEAGb9ECWmEzf6FQbrBZ9w7lshQhqowtrbLDFw4rXAxZuE="
]


def verify_signature(command: WASignedCommand) -> bool:
    """
    Verify Ed25519 signature on the command.

    Args:
        command: The signed command to verify

    Returns:
        True if signature is valid, False otherwise
    """
    if not CRYPTO_AVAILABLE:
        logger.error("Crypto not available - cannot verify signature")
        return False

    try:
        # Decode the public key (handle URL-safe base64)
        # Add padding if needed
        key_b64 = command.wa_public_key
        key_b64 += "=" * (4 - len(key_b64) % 4) if len(key_b64) % 4 else ""
        public_key_bytes = base64.urlsafe_b64decode(key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

        # Build the message that was signed
        # This must match exactly what was signed on the client side
        message_data: JSONDict = {
            "command_id": command.command_id,
            "command_type": command.command_type.value,  # Use enum value
            "wa_id": command.wa_id,
            "issued_at": command.issued_at.isoformat(),
            "reason": command.reason,
            "target_agent_id": command.target_agent_id,
        }
        if command.expires_at:
            message_data["expires_at"] = command.expires_at.isoformat()
        if command.target_tree_path:
            # target_tree_path is List[str], not str
            message_data["target_tree_path"] = command.target_tree_path

        message = json.dumps(message_data, sort_keys=True).encode()

        # Decode and verify signature (handle URL-safe base64)
        sig_b64 = command.signature
        sig_b64 += "=" * (4 - len(sig_b64) % 4) if len(sig_b64) % 4 else ""
        signature_bytes = base64.urlsafe_b64decode(sig_b64)

        # Debug logging
        logger.info(f"Message to verify: {message.decode()}")
        logger.info(f"Message bytes length: {len(message)}")
        logger.info(f"Signature bytes length: {len(signature_bytes)}")
        logger.info(f"Public key bytes length: {len(public_key_bytes)}")

        public_key.verify(signature_bytes, message)

        return True

    except InvalidSignature:
        logger.warning("Signature verification failed - Invalid signature")
        logger.warning(f"Public key (raw): {command.wa_public_key}")
        logger.warning(f"Signature (raw): {command.signature}")
        logger.warning(f"Message: {message.decode()}")
        return False
    except (ValueError, KeyError) as e:
        logger.warning(f"Signature verification failed - Decode error: {type(e).__name__}: {e}")
        logger.warning(f"Public key (raw): {command.wa_public_key}")
        logger.warning(f"Signature (raw): {command.signature}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during signature verification: {type(e).__name__}: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


def verify_timestamp(command: WASignedCommand, window_minutes: int = 5) -> bool:
    """
    Verify command timestamp is within acceptable window.

    Args:
        command: The command to verify
        window_minutes: Maximum age of command in minutes

    Returns:
        True if timestamp is valid, False otherwise
    """
    now = datetime.now(timezone.utc)

    # Check if command is too old
    if now - command.issued_at > timedelta(minutes=window_minutes):
        logger.warning(f"Command too old: issued at {command.issued_at}, now {now}")
        return False

    # Check if command is from the future (clock skew)
    if command.issued_at > now + timedelta(minutes=1):
        logger.warning(f"Command from future: issued at {command.issued_at}, now {now}")
        return False

    # Check expiration if set
    if command.expires_at and now > command.expires_at:
        logger.warning(f"Command expired at {command.expires_at}, now {now}")
        return False

    return True


def is_authorized_key(public_key: str) -> bool:
    """
    Check if the public key is authorized for emergency shutdown.

    In production, this would check against:
    - Root WA authority keys
    - Keys in the trust tree
    - Dynamically configured emergency keys

    Args:
        public_key: Base64 encoded public key

    Returns:
        True if key is authorized
    """
    # For now, just check against hardcoded root WA keys
    # In production, this would be more sophisticated
    return public_key in ROOT_WA_AUTHORITY_KEYS


@router.post("/emergency/shutdown", response_model=SuccessResponse[EmergencyShutdownStatus])
async def emergency_shutdown(command: WASignedCommand, request: Request) -> SuccessResponse[EmergencyShutdownStatus]:
    """
    Execute emergency shutdown with cryptographically signed command.

    This endpoint requires no authentication - the signature IS the authentication.
    Only accepts SHUTDOWN_NOW commands signed by authorized Wise Authorities.

    Security checks:
    1. Valid Ed25519 signature
    2. Timestamp within 5-minute window
    3. Public key is authorized (ROOT WA or in trust tree)
    4. Command type is SHUTDOWN_NOW

    Args:
        command: Cryptographically signed shutdown command

    Returns:
        Status of the emergency shutdown process

    Raises:
        HTTPException: If any security check fails
    """
    logger.critical(f"Emergency shutdown requested by WA {command.wa_id}")
    logger.info(f"Command details: type={command.command_type}, issued_at={command.issued_at}, reason={command.reason}")

    # Initialize status
    status = EmergencyShutdownStatus(command_received=datetime.now(timezone.utc), command_verified=False)

    # Verify command type
    if command.command_type != EmergencyCommandType.SHUTDOWN_NOW:
        status.verification_error = f"Invalid command type: {command.command_type}"
        logger.error(status.verification_error)
        raise HTTPException(status_code=400, detail=status.verification_error)

    # Verify timestamp
    if not verify_timestamp(command):
        status.verification_error = "Command timestamp outside acceptable window"
        logger.error(status.verification_error)
        raise HTTPException(status_code=403, detail=status.verification_error)

    # Verify signature
    if not verify_signature(command):
        status.verification_error = "Invalid signature"
        logger.error(status.verification_error)
        raise HTTPException(status_code=403, detail=status.verification_error)

    # Verify authority
    if not is_authorized_key(command.wa_public_key):
        status.verification_error = "Unauthorized public key"
        logger.error(status.verification_error)
        raise HTTPException(status_code=403, detail=status.verification_error)

    # All checks passed
    status.command_verified = True
    logger.info("Emergency shutdown command verified successfully")

    # Get runtime control service if available
    runtime_service = None
    service_registry = getattr(request.app.state, "service_registry", None)
    if service_registry:
        try:
            from ciris_engine.schemas.runtime.enums import ServiceType

            runtime_service = await service_registry.get_service(
                handler="emergency", service_type=ServiceType.RUNTIME_CONTROL
            )
        except Exception as e:
            logger.warning(f"RuntimeControlService not available: {e}")

    # If we have runtime control service, use it
    if runtime_service and hasattr(runtime_service, "handle_emergency_shutdown"):
        try:
            logger.info("Delegating to RuntimeControlService for emergency shutdown")
            status = await runtime_service.handle_emergency_shutdown(command)
            return SuccessResponse(data=status)
        except Exception as e:
            logger.error(f"RuntimeControlService emergency shutdown failed: {e}")
            # Fall through to direct shutdown

    # Otherwise, perform direct shutdown
    logger.warning("No RuntimeControlService - performing direct shutdown")

    try:
        # Get shutdown service directly from runtime
        runtime = getattr(request.app.state, "runtime", None)
        if not runtime:
            raise HTTPException(status_code=503, detail="Runtime not available")

        shutdown_service = getattr(runtime, "shutdown_service", None)
        if not shutdown_service:
            raise HTTPException(status_code=503, detail=ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE)

        # Mark shutdown initiated
        status.shutdown_initiated = datetime.now(timezone.utc)

        # Request immediate emergency shutdown (forced termination)
        reason = f"EMERGENCY: {command.reason} (WA: {command.wa_id})"
        await shutdown_service.emergency_shutdown(reason)

        # Update status
        status.services_stopped = ["shutdown_requested"]
        status.data_persisted = True
        status.final_message_sent = True
        status.shutdown_completed = datetime.now(timezone.utc)
        status.exit_code = 0

        logger.critical("Emergency shutdown initiated successfully")
        return SuccessResponse(data=status)

    except Exception as e:
        logger.error(f"Emergency shutdown failed: {e}")
        status.verification_error = f"Shutdown failed: {str(e)}"
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emergency/test")
async def test_emergency_endpoint() -> JSONDict:
    """
    Test endpoint to verify emergency routes are mounted.

    This endpoint requires no authentication and simply confirms
    the emergency routes are accessible.
    """
    return {
        "status": "ok",
        "message": "Emergency endpoint accessible",
        "crypto_available": CRYPTO_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
