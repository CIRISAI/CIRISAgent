"""Device authentication and node connection for CIRIS setup.

This module handles the device auth flow with CIRISPortal, including:
- Session persistence for app restarts
- CIRISVerify attestation submission
- Key activation and binding
- Licensed package download
"""

import json
import logging
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status

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
    """Validate portal URL to prevent SSRF attacks.

    Only allows requests to trusted CIRIS Portal domains.
    This prevents attackers from using the agent as a proxy to access
    internal services, cloud metadata endpoints, or other untrusted hosts.

    Args:
        url: The portal URL to validate

    Returns:
        The validated URL

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

    return url


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
# CIRISVerify Attestation (inline helpers for connect_node)
# ============================================================================


async def _submit_attestation_inline(challenge_nonce: str, device_code: str, portal_url: str) -> None:
    """Submit CIRISVerify hardware attestation to Portal inline during connect-node.

    Runs CIRISVerify on an 8MB-stack thread (iOS Rust/Tokio compatibility),
    then POSTs the proof to Portal's /api/device/attest.

    Non-fatal: if CIRISVerify is unavailable (community mode) or Portal
    rejects the proof, we log and continue — the user can still authorize.
    """
    import threading

    import httpx

    # Validate portal URL to prevent SSRF
    try:
        _validate_portal_url(portal_url)
    except ValueError as e:
        logger.warning("Invalid portal URL for attestation: %s", e)
        return

    challenge_bytes = bytes.fromhex(challenge_nonce)

    # Attempt attestation on 8MB stack thread (Rust Tokio runtime needs it)
    attest_result: List[Any] = [None, None]  # [proof_dict | None, error | None]

    def _attest_on_large_stack() -> None:
        try:
            from ciris_verify import CIRISVerify as CV

            verifier = CV(skip_integrity_check=True)
            proof = verifier.export_attestation_sync(challenge_bytes)
            attest_result[0] = proof  # export_attestation_sync returns dict directly
        except Exception as e:
            attest_result[1] = e

    old_stack = threading.stack_size()
    try:
        threading.stack_size(8 * 1024 * 1024)  # 8 MB
        t = threading.Thread(target=_attest_on_large_stack, daemon=True)
        t.start()
        t.join(timeout=15)
    finally:
        threading.stack_size(old_stack)

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

    # POST proof to Portal's /api/device/attest
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            attest_resp = await client.post(
                f"{portal_url.rstrip('/')}/api/device/attest",
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


def _decode_private_key(private_key_b64: str) -> Optional[bytes]:
    """Decode and validate a base64-encoded Ed25519 private key."""
    import base64

    try:
        key_bytes = base64.b64decode(private_key_b64)
        if len(key_bytes) != 32:
            logger.warning(
                "Key activation skipped: invalid key length (%d bytes, expected 32)",
                len(key_bytes),
            )
            return None
        return key_bytes
    except Exception as e:
        logger.warning("Key activation skipped: failed to decode key: %s", e)
        return None


def _import_key_and_generate_attestation(
    key_bytes: bytes, challenge_bytes: bytes
) -> tuple[Optional[Dict[str, Any]], Optional[Exception]]:
    """Import key into CIRISVerify and generate attestation proof.

    Returns (proof_dict, error) - one will be None.
    """
    try:
        from ciris_verify import CIRISVerify as CV

        logger.info("[KEY-IMPORT] Creating CIRISVerify instance...")
        verifier = CV(skip_integrity_check=True)

        # Import the Portal-issued key
        logger.info(f"[KEY-IMPORT] Calling import_key_sync() with {len(key_bytes)} byte key...")
        verifier.import_key_sync(key_bytes)
        logger.info("[KEY-IMPORT] import_key_sync() completed")

        # Reset UnifiedSigningKey singleton to use portal key
        from ciris_engine.logic.audit.signing_protocol import reset_unified_signing_key

        reset_unified_signing_key()
        logger.info("[KEY-IMPORT] UnifiedSigningKey singleton reset")

        # Verify key was imported
        if hasattr(verifier, "has_key_sync") and not verifier.has_key_sync():
            logger.error("[KEY-IMPORT] CRITICAL: Key import succeeded but has_key_sync() returns False!")

        # Get Ed25519 key fingerprint
        key_fingerprint_hex = _get_key_fingerprint(verifier)

        # Generate attestation proof
        proof = _generate_attestation_proof(verifier, challenge_bytes, key_fingerprint_hex)

        key_type = proof.get("key_type", "unknown") if isinstance(proof, dict) else "unknown"
        logger.info(f"[KEY-IMPORT] Attestation generated: key_type={key_type}")
        return proof, None

    except Exception as e:
        logger.error(f"[KEY-IMPORT] Exception during key import: {type(e).__name__}: {e}")
        return None, e


def _get_key_fingerprint(verifier: Any) -> Optional[str]:
    """Get Ed25519 key fingerprint from verifier."""
    try:
        if hasattr(verifier, "get_ed25519_public_key_sync"):
            import hashlib

            ed25519_pubkey = verifier.get_ed25519_public_key_sync()
            if ed25519_pubkey:
                fingerprint = hashlib.sha256(ed25519_pubkey).hexdigest()
                logger.info(f"[KEY-IMPORT] Ed25519 fingerprint: {fingerprint[:16]}...")
                return fingerprint
    except Exception as key_err:
        logger.warning(f"[KEY-IMPORT] Could not get Ed25519 fingerprint: {key_err}")
    return None


def _generate_attestation_proof(
    verifier: Any, challenge_bytes: bytes, key_fingerprint_hex: Optional[str]
) -> Dict[str, Any]:
    """Generate attestation proof using CIRISVerify."""
    import ciris_engine

    agent_version = getattr(ciris_engine, "__version__", "0.0.0")
    agent_root = os.environ.get("CIRIS_AGENT_ROOT", os.environ.get("CIRIS_HOME", "/app"))

    if hasattr(verifier, "run_attestation_sync"):
        result: Dict[str, Any] = verifier.run_attestation_sync(
            challenge=challenge_bytes,
            agent_version=agent_version,
            agent_root=agent_root,
            spot_check_count=0,
            key_fingerprint=key_fingerprint_hex,
        )
        return result
    else:
        logger.warning("[KEY-IMPORT] run_attestation_sync not available, using export_attestation_sync")
        result = verifier.export_attestation_sync(challenge_bytes)
        return result


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


def _log_key_type_status(proof_dict: Dict[str, Any]) -> None:
    """Log the key type status from attestation proof."""
    key_type = proof_dict.get("key_type", "unknown")
    if key_type not in ("portal", "registry_unavailable"):
        logger.warning(
            "Key activation: unexpected key_type '%s' (expected 'portal' or 'registry_unavailable'). "
            "Key may not have been imported correctly.",
            key_type,
        )
    elif key_type == "registry_unavailable":
        logger.info("Key activation: registry unavailable, key will be verified when online.")


async def _submit_activation_to_portal(validated_portal_url: str, device_code: str, proof_dict: Dict[str, Any]) -> None:
    """Submit key activation to Portal API."""
    import httpx

    # NOSONAR - URL is pre-validated by _validate_portal_url() which ensures trusted hosts only
    activate_url = urllib.parse.urljoin(validated_portal_url.rstrip("/") + "/", "api/device/activate")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            activate_resp = await client.post(
                activate_url,
                json={"device_code": device_code, "attestation_proof": proof_dict},
            )
            _handle_activation_response(activate_resp)
    except httpx.HTTPError as e:
        logger.warning("Failed to submit key activation to Portal: %s", e)


def _handle_activation_response(response: Any) -> None:
    """Handle Portal activation response."""
    if response.status_code == 200:
        result_data = response.json()
        logger.info(
            "Portal key activation result: activated=%s, key_id=%s",
            result_data.get("activated", False),
            result_data.get("key_id", "unknown"),
        )
    elif response.status_code == 403:
        result_data = response.json()
        error = result_data.get("error", "unknown")
        if "KEY REUSE" in error:
            logger.error(
                "KEY REUSE DETECTED: %s. This key was already activated "
                "for another agent. Key reuse is forbidden for CIRIS agents.",
                error,
            )
        else:
            logger.warning("Portal key activation rejected: %s", error)
    else:
        logger.warning("Portal key activation failed: HTTP %s", response.status_code)


async def _activate_key_inline(private_key_b64: str, device_code: str, portal_url: str) -> None:
    """Phase 2: Key Activation - import Portal key and submit second attestation.

    After receiving the signing key from Portal, we:
    1. Import it into CIRISVerify
    2. Generate a second attestation (signed with Portal key, key_type="portal")
    3. Submit to /api/device/activate

    This creates a tamper-evident binding between the agent instance and its key.
    Key reuse across agents is FORBIDDEN - Portal tracks all activations.
    """
    import httpx

    # Validate portal URL (SSRF protection)
    try:
        validated_portal_url = _validate_portal_url(portal_url)
    except ValueError as e:
        logger.warning("Invalid portal URL for key activation: %s", e)
        return

    # Decode and validate the private key
    key_bytes = _decode_private_key(private_key_b64)
    if key_bytes is None:
        return

    # Generate challenge and run key import on large stack thread
    challenge_bytes = os.urandom(32)
    activation_result: List[Any] = [None, None]

    def _run_import() -> None:
        proof, error = _import_key_and_generate_attestation(key_bytes, challenge_bytes)
        activation_result[0] = proof
        activation_result[1] = error

    is_ios = os.environ.get("CIRIS_IOS_FRAMEWORK_PATH") is not None
    timeout = 25 if is_ios else 15
    _run_on_large_stack(_run_import, timeout)

    # Check for errors
    proof_dict, error = activation_result
    if error is not None or proof_dict is None:
        error_msg = str(error) if error else "CIRISVerify activation timed out"
        logger.warning("Key activation skipped: %s", error_msg)
        return

    # Log key type status
    _log_key_type_status(proof_dict)

    # Submit activation to Portal
    await _submit_activation_to_portal(validated_portal_url, device_code, proof_dict)


# ============================================================================
# Device Auth Endpoints
# ============================================================================

# Note: These endpoints are registered in the legacy router for now.
# The functions are defined here but the @router decorators are applied
# in _setup_legacy.py to maintain backwards compatibility during migration.
