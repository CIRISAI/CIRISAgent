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


def _validate_portal_url(url: str) -> str:
    """Validate portal URL to prevent SSRF attacks.

    Args:
        url: The portal URL to validate

    Returns:
        The validated URL

    Raises:
        ValueError: If the URL is invalid or untrusted
    """
    parsed = urllib.parse.urlparse(url)

    # Must have scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid URL format")

    # Only allow https (or http for localhost in development)
    if parsed.scheme not in ("https", "http"):
        raise ValueError("URL must use https")

    # For http, only allow localhost/127.0.0.1 (development only)
    if parsed.scheme == "http":
        host = parsed.netloc.split(":")[0].lower()
        if host not in ("localhost", "127.0.0.1"):
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
                verified = result_data.get("verified", False)
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


async def _activate_key_inline(private_key_b64: str, device_code: str, portal_url: str) -> None:
    """Phase 2: Key Activation - import Portal key and submit second attestation.

    After receiving the signing key from Portal, we:
    1. Import it into CIRISVerify
    2. Generate a second attestation (signed with Portal key, key_type="portal")
    3. Submit to /api/device/activate

    This creates a tamper-evident binding between the agent instance and its key.
    Key reuse across agents is FORBIDDEN - Portal tracks all activations.
    Transferring agent identities to a new device is NOT SUPPORTED YET.

    Non-fatal: if activation fails, we log and continue — agent will still work
    but key reuse detection may not be fully enabled.
    """
    import base64
    import threading

    import httpx

    # Validate portal URL to prevent SSRF
    try:
        _validate_portal_url(portal_url)
    except ValueError as e:
        logger.warning("Invalid portal URL for key activation: %s", e)
        return

    # Decode the private key from base64
    try:
        key_bytes = base64.b64decode(private_key_b64)
        if len(key_bytes) != 32:
            logger.warning(
                "Key activation skipped: invalid key length (%d bytes, expected 32)",
                len(key_bytes),
            )
            return
    except Exception as e:
        logger.warning("Key activation skipped: failed to decode key: %s", e)
        return

    # Generate a fresh challenge for the second attestation
    challenge_bytes = os.urandom(32)

    # Import key and generate attestation on 8MB stack thread
    # [proof_dict, error, has_key_before, has_key_after]
    activate_result: List[Any] = [None, None, None, None]

    def _activate_on_large_stack() -> None:
        try:
            from ciris_verify import CIRISVerify as CV

            logger.info("[KEY-IMPORT] Creating CIRISVerify instance...")
            verifier = CV(skip_integrity_check=True)

            # Check key state BEFORE import
            has_key_before = False
            if hasattr(verifier, "has_key_sync"):
                has_key_before = verifier.has_key_sync()
            activate_result[2] = has_key_before
            logger.info(f"[KEY-IMPORT] has_key_sync() BEFORE import: {has_key_before}")

            # Import the Portal-issued key into Android Keystore
            logger.info(f"[KEY-IMPORT] Calling import_key_sync() with {len(key_bytes)} byte key...")
            verifier.import_key_sync(key_bytes)
            logger.info("[KEY-IMPORT] import_key_sync() completed")

            # Reset UnifiedSigningKey singleton to force re-initialization with portal key
            # This fixes startup order bug where singleton cached a generated key before portal import
            from ciris_engine.logic.audit.signing_protocol import reset_unified_signing_key

            reset_unified_signing_key()
            logger.info("[KEY-IMPORT] UnifiedSigningKey singleton reset - will use portal key")

            # Check key state AFTER import
            has_key_after = False
            if hasattr(verifier, "has_key_sync"):
                has_key_after = verifier.has_key_sync()
            activate_result[3] = has_key_after
            logger.info(f"[KEY-IMPORT] has_key_sync() AFTER import: {has_key_after}")

            if not has_key_after:
                logger.error("[KEY-IMPORT] CRITICAL: Key import succeeded but has_key_sync() returns False!")
                logger.error("[KEY-IMPORT] This suggests the key was NOT persisted to Android Keystore")

            # Generate second attestation using run_attestation_sync which contacts registry
            # This ensures key_type is properly set to "portal" or "registry_unavailable"
            # (export_attestation_sync returns "persisted" since it doesn't contact registry)
            logger.info("[KEY-IMPORT] Generating attestation proof via run_attestation_sync...")

            # Get minimal agent info for attestation
            import ciris_engine

            agent_version = getattr(ciris_engine, "__version__", "0.0.0")
            agent_root = os.environ.get("CIRIS_AGENT_ROOT", os.environ.get("CIRIS_HOME", "/app"))

            # Get Ed25519 key fingerprint for registry verification
            key_fingerprint_hex = None
            try:
                if hasattr(verifier, "get_ed25519_public_key_sync"):
                    import hashlib

                    ed25519_pubkey = verifier.get_ed25519_public_key_sync()
                    if ed25519_pubkey:
                        key_fingerprint_hex = hashlib.sha256(ed25519_pubkey).hexdigest()
                        logger.info(f"[KEY-IMPORT] Ed25519 fingerprint: {key_fingerprint_hex[:16]}...")
            except Exception as key_err:
                logger.warning(f"[KEY-IMPORT] Could not get Ed25519 fingerprint: {key_err}")

            # Use run_attestation_sync if available (v0.6.17+), fallback to export_attestation_sync
            if hasattr(verifier, "run_attestation_sync"):
                proof = verifier.run_attestation_sync(
                    challenge=challenge_bytes,
                    agent_version=agent_version,
                    agent_root=agent_root,
                    spot_check_count=0,  # Skip file checks during key activation
                    key_fingerprint=key_fingerprint_hex,
                )
            else:
                # Fallback for older CIRISVerify versions
                logger.warning("[KEY-IMPORT] run_attestation_sync not available, using export_attestation_sync")
                proof = verifier.export_attestation_sync(challenge_bytes)

            key_type = proof.get("key_type", "unknown") if isinstance(proof, dict) else "unknown"
            logger.info(f"[KEY-IMPORT] Attestation generated: key_type={key_type}")
            activate_result[0] = proof
        except Exception as e:
            logger.error(f"[KEY-IMPORT] Exception during key import: {type(e).__name__}: {e}")
            activate_result[1] = e

    # On Android, skip stack size manipulation (may not work with Chaquopy)
    # iOS + desktop need 8MB stack for Rust/Tokio runtime
    is_android = os.environ.get("ANDROID_ROOT") is not None
    is_ios = os.environ.get("CIRIS_IOS_FRAMEWORK_PATH") is not None
    join_timeout = 25 if (is_android or is_ios) else 15

    if is_android:
        t = threading.Thread(target=_activate_on_large_stack, daemon=True)
        t.start()
        t.join(timeout=join_timeout)
    else:
        old_stack = threading.stack_size()
        try:
            threading.stack_size(8 * 1024 * 1024)  # 8 MB
            t = threading.Thread(target=_activate_on_large_stack, daemon=True)
            t.start()
            t.join(timeout=join_timeout)
        finally:
            threading.stack_size(old_stack)

    # Check for errors
    if activate_result[1] is not None or activate_result[0] is None:
        error_msg = str(activate_result[1]) if activate_result[1] else "CIRISVerify activation timed out"
        logger.warning("Key activation skipped: %s", error_msg)
        return

    proof_dict = activate_result[0]

    # Verify key_type indicates portal key (portal=verified, registry_unavailable=offline)
    key_type = proof_dict.get("key_type", "unknown")
    if key_type not in ("portal", "registry_unavailable"):
        logger.warning(
            "Key activation: unexpected key_type '%s' (expected 'portal' or 'registry_unavailable'). "
            "Key may not have been imported correctly.",
            key_type,
        )
    elif key_type == "registry_unavailable":
        logger.info("Key activation: registry unavailable, key will be verified when online.")

    # POST to Portal's /api/device/activate
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            activate_resp = await client.post(
                f"{portal_url.rstrip('/')}/api/device/activate",
                json={
                    "device_code": device_code,
                    "attestation_proof": proof_dict,
                },
            )

            if activate_resp.status_code == 200:
                result_data = activate_resp.json()
                activated = result_data.get("activated", False)
                logger.info(
                    "Portal key activation result: activated=%s, key_id=%s",
                    activated,
                    result_data.get("key_id", "unknown"),
                )
            elif activate_resp.status_code == 403:
                result_data = activate_resp.json()
                error = result_data.get("error", "unknown")
                # Check for key reuse
                if "KEY REUSE" in error:
                    logger.error(
                        "KEY REUSE DETECTED: %s. This key was already activated "
                        "for another agent. Key reuse is forbidden for CIRIS agents.",
                        error,
                    )
                else:
                    logger.warning("Portal key activation rejected: %s", error)
            else:
                logger.warning("Portal key activation failed: HTTP %s", activate_resp.status_code)
    except httpx.HTTPError as e:
        logger.warning("Failed to submit key activation to Portal: %s", e)


# ============================================================================
# Device Auth Endpoints
# ============================================================================

# Note: These endpoints are registered in the legacy router for now.
# The functions are defined here but the @router decorators are applied
# in _setup_legacy.py to maintain backwards compatibility during migration.
