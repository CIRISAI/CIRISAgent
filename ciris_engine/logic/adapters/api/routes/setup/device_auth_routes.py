"""Licensed package download endpoint for CIRIS setup.

The device auth flow (connect-node, connect-node/status, reset-device-auth)
is served natively by the local ciris-server node on port 4243; the Kotlin
client drives those endpoints on the node directly. Only the licensed
package download remains on the brain (:8080) — the node has no route for
it yet.
"""

import hashlib
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

from fastapi import APIRouter

from ciris_engine.schemas.api.responses import SuccessResponse

from .._common import RESPONSES_500
from .dependencies import SetupOnlyDep
from .device_auth import ALLOWED_PORTAL_HOSTS
from .models import DownloadPackageRequest, DownloadPackageResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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
