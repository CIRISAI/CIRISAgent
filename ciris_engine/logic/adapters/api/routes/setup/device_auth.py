"""Device authentication and node connection for CIRIS setup.

This module handles the device auth flow with CIRISPortal, including:
- Session persistence for app restarts
- CIRISVerify attestation submission
- Self-custody key registration (FSD-002)

SECURITY: This module implements SELF-CUSTODY key management.
- The agent generates its own Ed25519 keypair
- Only the PUBLIC key is registered with Portal
- The PRIVATE key NEVER leaves the agent
- Portal NEVER issues or receives private keys
"""

import hashlib
import json
import logging
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from ciris_engine.schemas.api.responses import SuccessResponse

# Trusted Portal domains for SSRF protection
# Only these hosts are allowed for device auth and package download
ALLOWED_PORTAL_HOSTS = frozenset(
    {
        "portal.ciris.ai",
        "portal.ciris-services-1.ai",
        "portal.ciris-services-2.ai",
        "localhost",
        "127.0.0.1",
    }
)


def _validate_portal_url(url: str) -> str:
    """Validate portal URL and return sanitized base URL.

    Only allows requests to trusted CIRIS Portal domains.
    This prevents attackers from using the agent as a proxy to access
    internal services, cloud metadata endpoints, or other untrusted hosts.

    SECURITY: Returns a reconstructed URL from validated components only,
    not the original user input. This prevents URL injection attacks.

    Args:
        url: The portal URL to validate

    Returns:
        A sanitized base URL constructed from validated components only

    Raises:
        ValueError: If the URL is invalid or not a trusted Portal domain
    """
    parsed = urllib.parse.urlparse(url)

    # Must have scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid URL format")

    # Only allow https (or http for localhost in development)
    if parsed.scheme not in ("https", "http"):
        raise ValueError("URL must use https")

    # Extract hostname (without port)
    host = parsed.netloc.split(":")[0].lower()

    # SECURITY: Only allow trusted Portal domains (prevents SSRF)
    if host not in ALLOWED_PORTAL_HOSTS:
        raise ValueError(
            f"Untrusted host '{host}'. Only CIRIS Portal domains are allowed: "
            f"{', '.join(sorted(ALLOWED_PORTAL_HOSTS))}"
        )

    # For http, only allow localhost/127.0.0.1 (development only)
    if parsed.scheme == "http" and host not in ("localhost", "127.0.0.1"):
        raise ValueError("HTTP only allowed for localhost")

    # SECURITY: Reconstruct URL from validated components only (prevents injection)
    # Only use scheme + netloc, discard any path/query/fragment from user input
    sanitized_url = f"{parsed.scheme}://{parsed.netloc}"
    return sanitized_url


from .models import (
    ConnectNodeRequest,
    ConnectNodeResponse,
    ConnectNodeStatusResponse,
    DownloadPackageRequest,
    DownloadPackageResponse,
)

logger = logging.getLogger(__name__)

# Create a sub-router for device auth endpoints
router = APIRouter()


# ============================================================================
# Device Auth Session Persistence
# ============================================================================


def _get_device_auth_session_path() -> Path:
    """Get path to the device auth session file."""
    ciris_home = os.environ.get("CIRIS_HOME", str(Path.home() / ".ciris"))
    return Path(ciris_home) / ".device_auth_session.json"


def _load_device_auth_session() -> Optional[Dict[str, Any]]:
    """Load active device auth session if it exists and hasn't expired."""
    session_path = _get_device_auth_session_path()
    if not session_path.exists():
        return None

    try:
        with open(session_path, "r") as f:
            session: Dict[str, Any] = json.load(f)

        # Check if expired
        expires_at = session.get("expires_at", 0)
        if time.time() > expires_at:
            logger.info("Device auth session expired, clearing")
            _clear_device_auth_session()
            return None

        return session
    except Exception as e:
        logger.warning("Failed to load device auth session: %s", e)
        return None


def _save_device_auth_session(
    device_code: str,
    portal_url: str,
    verification_uri_complete: str,
    user_code: str,
    expires_in: int,
    interval: int,
) -> None:
    """Save active device auth session."""
    session_path = _get_device_auth_session_path()
    session = {
        "device_code": device_code,
        "portal_url": portal_url,
        "verification_uri_complete": verification_uri_complete,
        "user_code": user_code,
        "expires_in": expires_in,
        "interval": interval,
        "expires_at": time.time() + expires_in,
        "created_at": time.time(),
    }

    try:
        session_path.parent.mkdir(parents=True, exist_ok=True)
        with open(session_path, "w") as f:
            json.dump(session, f)
        logger.info("Saved device auth session (expires in %ds)", expires_in)
    except Exception as e:
        logger.warning("Failed to save device auth session: %s", e)


def _clear_device_auth_session() -> None:
    """Clear device auth session (on completion or error)."""
    session_path = _get_device_auth_session_path()
    try:
        if session_path.exists():
            session_path.unlink()
            logger.info("Cleared device auth session")
    except Exception as e:
        logger.warning("Failed to clear device auth session: %s", e)


# ============================================================================
# Large Stack Thread Helper (for Rust/Tokio compatibility)
# ============================================================================


def _run_on_large_stack(func: Any, timeout: float) -> None:
    """Run function on a thread with large stack (8MB for Rust/Tokio)."""
    import threading

    is_android = os.environ.get("ANDROID_ROOT") is not None

    if is_android:
        t = threading.Thread(target=func, daemon=True)
        t.start()
        t.join(timeout=timeout)
    else:
        old_stack = threading.stack_size()
        try:
            threading.stack_size(8 * 1024 * 1024)
            t = threading.Thread(target=func, daemon=True)
            t.start()
            t.join(timeout=timeout)
        finally:
            threading.stack_size(old_stack)


# ============================================================================
# CIRISVerify Attestation (Phase 1: Hardware attestation during device auth)
# ============================================================================


async def _submit_attestation_inline(challenge_nonce: str, device_code: str, portal_url: str) -> None:
    """Submit CIRISVerify hardware attestation to Portal inline during connect-node.

    Runs CIRISVerify on an 8MB-stack thread (iOS Rust/Tokio compatibility),
    then POSTs the proof to Portal's /api/device/attest.

    Non-fatal: if CIRISVerify is unavailable (community mode) or Portal
    rejects the proof, we log and continue — the user can still authorize.
    """
    import httpx

    # Validate portal URL and get sanitized base (SSRF protection)
    try:
        safe_portal_url = _validate_portal_url(portal_url)
    except ValueError as e:
        logger.warning("Invalid portal URL for attestation: %s", e)
        return

    challenge_bytes = bytes.fromhex(challenge_nonce)

    # Attempt attestation on 8MB stack thread (Rust Tokio runtime needs it)
    attest_result: List[Any] = [None, None]  # [proof_dict | None, error | None]

    def _attest_on_large_stack() -> None:
        try:
            from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

            verifier = get_verifier()
            if verifier is None:
                attest_result[1] = RuntimeError("CIRISVerify singleton not available")
                return
            proof = verifier.export_attestation_sync(challenge_bytes)
            attest_result[0] = proof  # export_attestation_sync returns dict directly
        except Exception as e:
            attest_result[1] = e

    _run_on_large_stack(_attest_on_large_stack, timeout=15)

    # CIRISVerify not available — skip gracefully (community mode)
    if attest_result[1] is not None or attest_result[0] is None:
        error_msg = str(attest_result[1]) if attest_result[1] else "CIRISVerify init timed out"
        logger.info("CIRISVerify attestation skipped (community mode): %s", error_msg)
        return

    proof_dict = attest_result[0]

    # Log attestation proof details for debugging
    logger.info(
        "[CIRISVerify] Attestation proof generated: key_type=%s, hw_algo=%s, hw_type=%s, "
        "pubkey_len=%d, sig_len=%d, challenge_len=%d",
        proof_dict.get("key_type", "unknown"),
        proof_dict.get("hardware_algorithm", "unknown"),
        proof_dict.get("hardware_type", "unknown"),
        len(proof_dict.get("hardware_public_key", "")),
        len(proof_dict.get("classical_signature", "")),
        len(proof_dict.get("challenge", "")),
    )

    # POST proof to Portal's /api/device/attest (using sanitized URL)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            attest_resp = await client.post(
                f"{safe_portal_url}/api/device/attest",
                json={
                    "device_code": device_code,
                    "attestation_proof": proof_dict,
                    "agent_hash": "",  # Will be populated after RegisterBuild
                    "integrity_passed": True,
                },
            )

            if attest_resp.status_code == 200:
                result_data = attest_resp.json()
                hw_type = result_data.get("hardware_type", "unknown")
                warnings = result_data.get("warnings", [])
                logger.info("[CIRISVerify] Portal attestation VERIFIED: hw_type=%s, warnings=%s", hw_type, warnings)
            else:
                # Log detailed error response from Portal
                try:
                    error_data = attest_resp.json()
                    errors = error_data.get("errors", [])
                    warnings = error_data.get("warnings", [])
                    logger.warning(
                        "[CIRISVerify] Portal attestation REJECTED: HTTP %s, errors=%s, warnings=%s",
                        attest_resp.status_code,
                        errors,
                        warnings,
                    )
                except Exception:
                    logger.warning(
                        "[CIRISVerify] Portal attestation rejected: HTTP %s, body=%s",
                        attest_resp.status_code,
                        attest_resp.text[:500],
                    )
    except httpx.HTTPError as e:
        logger.warning("[CIRISVerify] Failed to submit attestation to Portal: %s", e)


# ============================================================================
# Self-Custody Key Registration (FSD-002)
#
# SECURITY ARCHITECTURE:
# - Agent generates its own Ed25519 keypair via CIRISVerify
# - Private key is TPM-protected and NEVER leaves the agent
# - Only the PUBLIC key is registered with Portal
# - Portal NEVER issues, receives, or handles private keys
# - This eliminates key custody liability entirely
# ============================================================================


def _get_public_key_from_verifier() -> tuple[Optional[bytes], Optional[Exception]]:
    """Get the Ed25519 public key from CIRISVerify.

    The keypair was already generated during CIRISVerify initialization.
    We promote it to permanent identity by registering the PUBLIC key with Portal.
    The PRIVATE key never leaves the agent (TPM-protected).

    Returns:
        (public_key_bytes, error) - error is None on success
    """
    try:
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

        verifier = get_verifier()
        if verifier is None:
            return None, RuntimeError("CIRISVerify singleton not available")

        # Get the public key (this is what we register with Portal)
        public_key = None
        if hasattr(verifier, "get_ed25519_public_key_sync"):
            public_key = verifier.get_ed25519_public_key_sync()

        if public_key is None:
            return None, RuntimeError("No Ed25519 public key available from CIRISVerify")

        return public_key, None

    except Exception as e:
        return None, e


def _sign_with_verifier(message: bytes) -> tuple[Optional[bytes], Optional[Exception]]:
    """Sign a message using the CIRISVerify Ed25519 key.

    The private key never leaves CIRISVerify (TPM-protected).

    Returns:
        (signature_bytes, error) - error is None on success
    """
    try:
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

        verifier = get_verifier()
        if verifier is None:
            return None, RuntimeError("CIRISVerify singleton not available")

        # Sign using CIRISVerify's Ed25519 key
        if hasattr(verifier, "sign_ed25519_sync"):
            signature = verifier.sign_ed25519_sync(message)
            return signature, None
        elif hasattr(verifier, "sign_sync"):
            signature = verifier.sign_sync(message)
            return signature, None
        else:
            return None, RuntimeError("CIRISVerify.sign_ed25519_sync not available")

    except Exception as e:
        return None, e


async def _register_self_custody_key(device_code: str, portal_url: str) -> Optional[str]:
    """Self-Custody Key Registration (FSD-002).

    After device auth completes, the agent:
    1. Gets its Ed25519 PUBLIC key from CIRISVerify
    2. Signs a registration message to prove possession
    3. Calls Portal /api/device/register-key to register the public key
    4. Signs the activation_challenge from Portal
    5. Calls Portal /api/device/activate-key to activate

    The PRIVATE key NEVER leaves the agent. Portal only sees the public key.

    Returns:
        key_id on success, None on failure
    """
    import httpx

    # Validate portal URL (SSRF protection)
    try:
        validated_portal_url = _validate_portal_url(portal_url)
    except ValueError as e:
        logger.warning("[SELF-CUSTODY] Invalid portal URL: %s", e)
        return None

    # Step 1: Get public key from CIRISVerify
    key_result: List[Any] = [None, None]  # [public_key, error]

    def _get_public_key() -> None:
        pub, err = _get_public_key_from_verifier()
        key_result[0] = pub
        key_result[1] = err

    _run_on_large_stack(_get_public_key, timeout=15)

    public_key, error = key_result
    if error is not None or public_key is None:
        error_msg = str(error) if error else "Failed to get public key"
        logger.warning("[SELF-CUSTODY] Key registration skipped: %s", error_msg)
        return None

    public_key_hex = public_key.hex()
    logger.info(
        "[SELF-CUSTODY] Got Ed25519 public key: %s...",
        public_key_hex[:16],
    )

    # Step 2: Generate agent_hash (for binding identity to build)
    agent_root = os.environ.get("CIRIS_AGENT_ROOT", os.environ.get("CIRIS_HOME", "/app"))
    import ciris_engine

    agent_version = getattr(ciris_engine, "__version__", "0.0.0")
    agent_hash = hashlib.sha256(f"{agent_root}:{agent_version}".encode()).hexdigest()

    # Step 3: Sign a registration message to prove we control the private key
    # Message format: "CIRIS_KEY_REGISTRATION:{device_code}:{public_key_hex}"
    registration_message = f"CIRIS_KEY_REGISTRATION:{device_code}:{public_key_hex}".encode()

    sign_result: List[Any] = [None, None]  # [signature, error]

    def _sign_registration() -> None:
        sig, err = _sign_with_verifier(registration_message)
        sign_result[0] = sig
        sign_result[1] = err

    _run_on_large_stack(_sign_registration, timeout=15)

    registration_signature, sign_error = sign_result
    if sign_error is not None or registration_signature is None:
        error_msg = str(sign_error) if sign_error else "Failed to sign registration"
        logger.warning("[SELF-CUSTODY] Registration signing failed: %s", error_msg)
        return None

    # Step 4: Call Portal /api/device/register-key
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            register_resp = await client.post(
                f"{validated_portal_url}/api/device/register-key",
                json={
                    "device_code": device_code,
                    "ed25519_public_key": public_key_hex,
                    "ed25519_signature": registration_signature.hex(),
                    "agent_hash": agent_hash,
                },
            )

            if register_resp.status_code != 200:
                body = register_resp.json() if register_resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = body.get("error", f"HTTP {register_resp.status_code}")
                logger.warning("[SELF-CUSTODY] Portal register-key failed: %s", error_msg)
                return None

            register_data = register_resp.json()
            key_id: str | None = register_data.get("key_id")
            activation_challenge_hex: str | None = register_data.get("activation_challenge")
            fingerprint = register_data.get("public_key_fingerprint")

            logger.info(
                "[SELF-CUSTODY] Key registered: key_id=%s, fingerprint=%s",
                key_id,
                fingerprint,
            )

    except httpx.HTTPError as e:
        logger.warning("[SELF-CUSTODY] Failed to register key with Portal: %s", e)
        return None

    if not key_id or not activation_challenge_hex:
        logger.warning("[SELF-CUSTODY] Portal did not return key_id or activation_challenge")
        return None

    # Step 5: Sign the activation challenge
    activation_challenge = bytes.fromhex(activation_challenge_hex)

    def _sign_activation() -> None:
        sig, err = _sign_with_verifier(activation_challenge)
        sign_result[0] = sig
        sign_result[1] = err

    _run_on_large_stack(_sign_activation, timeout=15)

    activation_signature, sign_error = sign_result
    if sign_error is not None or activation_signature is None:
        error_msg = str(sign_error) if sign_error else "Failed to sign activation challenge"
        logger.warning("[SELF-CUSTODY] Activation signing failed: %s", error_msg)
        return None

    # Step 6: Call Portal /api/device/activate-key
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            activate_resp = await client.post(
                f"{validated_portal_url}/api/device/activate-key",
                json={
                    "device_code": device_code,
                    "key_id": key_id,
                    "activation_challenge": activation_challenge_hex,
                    "ed25519_signature": activation_signature.hex(),
                    "agent_hash": agent_hash,
                },
            )

            if activate_resp.status_code == 200:
                result_data = activate_resp.json()
                logger.info(
                    "[SELF-CUSTODY] Key ACTIVATED: key_id=%s, message=%s",
                    result_data.get("key_id"),
                    result_data.get("message", "success"),
                )
                return key_id
            else:
                body = activate_resp.json() if activate_resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = body.get("error", f"HTTP {activate_resp.status_code}")
                logger.warning("[SELF-CUSTODY] Portal activate-key failed: %s", error_msg)
                return None

    except httpx.HTTPError as e:
        logger.warning("[SELF-CUSTODY] Failed to activate key with Portal: %s", e)
        return None


# ============================================================================
# Device Auth Endpoints
# ============================================================================

# Note: These endpoints are registered in the legacy router for now.
# The functions are defined here but the @router decorators are applied
# in _setup_legacy.py to maintain backwards compatibility during migration.
