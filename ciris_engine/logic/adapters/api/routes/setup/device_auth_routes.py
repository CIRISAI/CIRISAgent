"""Device authentication and package download endpoints for CIRIS setup.

This module provides endpoints for the device auth flow with CIRISPortal,
including connect-node, status polling, and licensed package download.
"""

import hashlib
import logging
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status

from ciris_engine.schemas.api.responses import SuccessResponse

from .._common import RESPONSES_500
from .dependencies import SetupOnlyDep
from .device_auth import (
    ALLOWED_PORTAL_HOSTS,
    _clear_device_auth_session,
    _load_device_auth_session,
    _register_self_custody_key,
    _save_device_auth_session,
    _submit_attestation_inline,
    _validate_portal_url,
)
from .models import (
    ConnectNodeRequest,
    ConnectNodeResponse,
    ConnectNodeStatusResponse,
    DownloadPackageRequest,
    DownloadPackageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/connect-node", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def connect_node(req: ConnectNodeRequest) -> SuccessResponse[ConnectNodeResponse]:
    """Initiate device auth via CIRISPortal.

    The user provides a Portal URL directly. This endpoint:
    1. Checks for existing non-expired device auth session (reuses if found)
    2. Normalizes the Portal URL (adds https:// if needed)
    3. Calls Portal's POST /api/device/authorize with agent info
    4. Persists the session so it survives app restarts
    5. Returns verification URL for user to open in browser

    CRITICAL: Device codes are persisted to survive app restarts. If user
    pays for a license in browser and app restarts, we must continue polling
    with the SAME device code, not request a new one.

    This endpoint is accessible without authentication during first-run.
    """
    import httpx

    raw_portal_url = req.node_url.strip().rstrip("/")
    # Normalize URL — add https:// if no scheme provided
    if not raw_portal_url.startswith("http://") and not raw_portal_url.startswith("https://"):
        raw_portal_url = f"https://{raw_portal_url}"

    # Validate and sanitize portal URL (SSRF protection)
    # Returns reconstructed URL from validated components only
    try:
        portal_url = _validate_portal_url(raw_portal_url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid portal URL: {e}",
        )

    # Check for existing non-expired session — reuse it if found
    existing_session = _load_device_auth_session()
    if existing_session and existing_session.get("portal_url") == portal_url:
        logger.info("Reusing existing device auth session (device_code=%s...)", existing_session["device_code"][:16])
        remaining = int(existing_session["expires_at"] - time.time())
        return SuccessResponse(
            data=ConnectNodeResponse(
                verification_uri_complete=existing_session["verification_uri_complete"],
                device_code=existing_session["device_code"],
                user_code=existing_session.get("user_code", ""),
                portal_url=portal_url,
                expires_in=max(remaining, 0),
                interval=existing_session.get("interval", 5),
            )
        )

    device_auth_endpoint = "/api/device/authorize"

    # For first-run setup, we send empty agent_info since we're provisioning a new agent.
    # Existing agents reconnecting would include their hash and public key here.
    agent_info: Dict[str, Any] = {}

    # Call Portal's device authorize endpoint directly
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            auth_resp = await client.post(
                f"{portal_url}{device_auth_endpoint}",
                json={
                    "portal_url": portal_url,
                    "agent_info": agent_info,
                },
            )
            auth_resp.raise_for_status()
            auth_data = auth_resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to initiate device auth with Portal at {portal_url}: {e}",
        )

    # If Portal returned a challenge_nonce, submit attestation inline
    # before returning to the client. This keeps KMP simple.
    challenge_nonce = auth_data.get("challenge_nonce")
    if challenge_nonce:
        await _submit_attestation_inline(
            challenge_nonce=challenge_nonce,
            device_code=auth_data["device_code"],
            portal_url=portal_url,
        )

    # Persist the session so it survives app restarts
    device_code = auth_data["device_code"]
    expires_in = auth_data.get("expires_in", 900)
    interval = auth_data.get("interval", 5)
    verification_uri = auth_data["verification_uri_complete"]
    user_code = auth_data.get("user_code", "")

    _save_device_auth_session(
        device_code=device_code,
        portal_url=portal_url,
        verification_uri_complete=verification_uri,
        user_code=user_code,
        expires_in=expires_in,
        interval=interval,
    )

    return SuccessResponse(
        data=ConnectNodeResponse(
            verification_uri_complete=verification_uri,
            device_code=device_code,
            user_code=user_code,
            portal_url=portal_url,
            expires_in=expires_in,
            interval=interval,
        )
    )


@router.get("/connect-node/status", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def connect_node_status(device_code: str, portal_url: str) -> SuccessResponse[ConnectNodeStatusResponse]:
    """Poll device auth status.

    Called periodically by the setup wizard to check if the user has
    completed the device auth flow in the Portal browser UI.

    Args:
        device_code: Opaque device code from /connect-node
        portal_url: Portal URL to poll (from node manifest)

    Returns:
        Status: pending (keep polling), complete (key ready), or error.
    """
    import httpx

    logger.info("[connect-node/status] Poll request received")

    # Validate portal URL and get sanitized base URL (SSRF protection)
    try:
        safe_base_url = _validate_portal_url(portal_url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid portal URL: {e}",
        )

    # Construct URL from sanitized base + hardcoded path (not user input)
    token_url = f"{safe_base_url}/api/device/token"
    logger.info("[connect-node/status] Calling Portal token endpoint")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            logger.info("[connect-node/status] Making POST request to Portal...")
            token_resp = await client.post(
                token_url,
                json={"device_code": device_code},
            )
            logger.info("[connect-node/status] Portal response status: %s", token_resp.status_code)
            logger.info("[connect-node/status] Portal response headers: %s", dict(token_resp.headers))

            # 428 = authorization_pending (RFC 8628)
            if token_resp.status_code == 428:
                logger.info("[connect-node/status] Portal returned 428 (authorization_pending) - keep polling")
                logger.info("[connect-node/status] ========== RETURNING PENDING ==========")
                return SuccessResponse(data=ConnectNodeStatusResponse(status="pending"))

            if token_resp.status_code == 403:
                # Authorization denied — clear session so user can retry
                _clear_device_auth_session()
                return SuccessResponse(data=ConnectNodeStatusResponse(status="error"))

            if token_resp.status_code != 200:
                body = (
                    token_resp.json()
                    if token_resp.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                error_desc = body.get("error_description", body.get("error", f"HTTP {token_resp.status_code}"))
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Portal token endpoint error: {error_desc}",
                )

            data = token_resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to poll Portal token endpoint: {e}",
        )

    # Success — extract provisioned data
    # NOTE: Portal no longer sends signing keys (FSD-002 self-custody)
    # Agent generates its own key and registers the PUBLIC key with Portal
    agent_record = data.get("agent_record", {})
    licensed_package = data.get("licensed_package") or {}
    registration_challenge = data.get("registration_challenge")  # Hex-encoded challenge from Portal

    # Log what Portal returned for debugging (non-sensitive metadata only)
    logger.info(
        "[connect-node/status] Portal returned agent_record=%s, has_challenge=%s",
        bool(agent_record),
        bool(registration_challenge),
    )

    # SELF-CUSTODY KEY REGISTRATION (FSD-002)
    # The agent's Ed25519 key was generated by CIRISVerify at startup.
    # We now register our PUBLIC key with Portal - the private key NEVER leaves the agent.
    logger.info("[connect-node/status] Starting self-custody key registration")
    key_id = await _register_self_custody_key(device_code, portal_url, registration_challenge)

    if key_id:
        logger.info("[connect-node/status] === KEY REGISTRATION SUCCESS ===")
        logger.info("[connect-node/status] Self-custody key registered: key_id=%s", key_id)
    else:
        logger.warning("[connect-node/status] === KEY REGISTRATION FAILED ===")
        logger.warning("[connect-node/status] Self-custody key registration failed (non-fatal for community mode)")

    # Clear device auth session — flow completed successfully
    _clear_device_auth_session()
    logger.info("Device auth flow completed successfully")

    return SuccessResponse(
        data=ConnectNodeStatusResponse(
            status="complete",
            template=agent_record.get("identity_template"),
            adapters=agent_record.get("approved_adapters"),
            org_id=data.get("org_id"),  # May be in top-level response now
            signing_key_b64=None,  # REMOVED: No private keys from Portal (self-custody)
            key_id=key_id,  # From self-custody registration
            stewardship_tier=agent_record.get("stewardship_tier"),
            package_download_url=licensed_package.get("download_url"),
            package_template_id=licensed_package.get("template_id"),
        )
    )


@router.post("/reset-device-auth", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def reset_device_auth() -> SuccessResponse[Dict[str, Any]]:
    """Reset device auth session state.

    Called when user backs out of the node auth flow (e.g., after timeout or cancel).
    This clears any stale device auth session to allow a fresh retry.

    No authentication required since this only affects local session state.
    """
    logger.info("Resetting device auth session (user backed out of node auth flow)")
    _clear_device_auth_session()

    return SuccessResponse(
        data={
            "status": "reset",
            "message": "Device auth session cleared",
        }
    )


@router.post("/download-package", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
async def download_package(req: DownloadPackageRequest) -> SuccessResponse[DownloadPackageResponse]:
    """Download and install a licensed module package from Portal.

    1. Downloads the zip from the Portal package endpoint
    2. Verifies checksum from response headers
    3. Unzips to the agent's licensed_modules/ directory
    4. Returns paths for template, modules, and config

    This endpoint is accessible without authentication during first-run.
    """
    import asyncio

    import httpx

    # Determine install directory
    data_dir = Path(os.environ.get("CIRIS_DATA_DIR", "."))
    licensed_modules_dir = data_dir / "licensed_modules"

    # Validate URL is from trusted Portal domains and paths only (security: prevent SSRF)
    # ALLOWED_PORTAL_HOSTS is imported from device_auth module
    ALLOWED_PATH_PREFIXES = ("/api/", "/v1/")  # Only allow API endpoints

    def _validate_and_reconstruct(raw_url: str) -> str:
        """Validate raw_url against the allowlists and return a URL reconstructed
        from validated components. Reconstruction is what closes the SSRF loop —
        validating components of the parsed URL but then requesting the original
        string lets parser-disagreement bugs (CVE-2023-24329-class) bypass the
        check. Raises ValueError on rejection.
        """
        p = urlparse(raw_url)
        if p.scheme not in ("https", "http"):
            raise ValueError(f"scheme '{p.scheme}' not allowed")
        host = (p.hostname or "").lower()
        if host not in ALLOWED_PORTAL_HOSTS:
            raise ValueError(f"host '{host}' not in allowed Portal domains")
        if p.scheme == "http" and host not in ("localhost", "127.0.0.1"):
            raise ValueError("http only allowed for localhost")
        if not any(p.path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
            raise ValueError("path must start with /api/ or /v1/")
        # Reconstruct from validated parts; preserve port + path + query, drop fragment + userinfo.
        netloc = host if p.port is None else f"{host}:{p.port}"
        suffix = f"?{p.query}" if p.query else ""
        return f"{p.scheme}://{netloc}{p.path}{suffix}"

    try:
        safe_download_url = _validate_and_reconstruct(req.package_download_url)
    except ValueError as e:
        return SuccessResponse(
            data=DownloadPackageResponse(status="error", error=f"Invalid package URL: {e}"),
        )

    try:
        # Download the zip from Portal
        # SECURITY: Disable follow_redirects to prevent redirect-based SSRF bypass
        # If Portal needs to redirect, it should redirect within allowed domains
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            headers: Dict[str, str] = {}
            if req.portal_session_cookie:
                headers["Cookie"] = req.portal_session_cookie

            dl_resp = await client.get(safe_download_url, headers=headers)

            # Handle redirects manually with validation
            if dl_resp.status_code in (301, 302, 303, 307, 308):
                redirect_url = dl_resp.headers.get("location", "")
                try:
                    safe_redirect_url = _validate_and_reconstruct(redirect_url)
                except ValueError as e:
                    return SuccessResponse(
                        data=DownloadPackageResponse(
                            status="error",
                            error=f"Redirect blocked: {e}",
                        )
                    )
                dl_resp = await client.get(safe_redirect_url, headers=headers)
            dl_resp.raise_for_status()

        # Get checksum from response header
        expected_checksum = dl_resp.headers.get("x-package-checksum", "")
        package_id = dl_resp.headers.get("x-package-id", "unknown")
        package_version = dl_resp.headers.get("x-package-version", "0.0.0")

        # Verify checksum
        actual_checksum = hashlib.sha256(dl_resp.content).hexdigest()
        if expected_checksum and actual_checksum != expected_checksum:
            return SuccessResponse(
                data=DownloadPackageResponse(
                    status="error",
                    error=f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}",
                )
            )

        # Save zip to temp file (run sync I/O in thread to avoid blocking event loop)
        def _write_temp_file(content: bytes) -> str:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(content)
                return tmp.name

        tmp_path = await asyncio.to_thread(_write_temp_file, dl_resp.content)

        # Create install directory
        install_dir = licensed_modules_dir / package_id
        if install_dir.exists():
            # Remove old version
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        # Unzip
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(install_dir)

        # Cleanup temp file
        os.unlink(tmp_path)

        logger.info(f"[Package Download] Installed {package_id} v{package_version} to {install_dir}")

        # Find key paths within the extracted package
        template_file = None
        modules_path = None
        config_path = None

        templates_dir = install_dir / "templates"
        if templates_dir.exists():
            yamls = list(templates_dir.glob("*.yaml"))
            if yamls:
                template_file = str(yamls[0])

        mods_dir = install_dir / "modules"
        if mods_dir.exists():
            modules_path = str(mods_dir)

        cfg_dir = install_dir / "config"
        if cfg_dir.exists():
            config_path = str(cfg_dir)

        return SuccessResponse(
            data=DownloadPackageResponse(
                status="success",
                package_path=str(install_dir),
                template_file=template_file,
                modules_path=modules_path,
                config_path=config_path,
                checksum=actual_checksum,
            )
        )

    except httpx.HTTPError as e:
        logger.error(f"[Package Download] HTTP error: {e}")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Failed to download package: {e}",
            )
        )
    except zipfile.BadZipFile:
        logger.error("[Package Download] Invalid zip file received")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error="Downloaded file is not a valid zip archive",
            )
        )
    except Exception as e:
        logger.error(f"[Package Download] Unexpected error: {e}")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Package installation failed: {e}",
            )
        )
