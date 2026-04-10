"""Attestation endpoints for CIRIS setup.

Delegates to AuthenticationService for CIRISVerify operations.
Eliminates duplicated verification logic from the old monolithic setup.py.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.attestation import AttestationResult

from .constants import CIRISVERIFY_NOT_AVAILABLE

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class VerifyStatusResponse(BaseModel):
    """CIRISVerify status for Trust and Security display.

    CIRISVerify is REQUIRED for CIRIS 2.0+. Agents cannot run without it.
    """

    loaded: bool = Field(..., description="Whether CIRISVerify library is loaded")
    version: Optional[str] = Field(None, description="CIRISVerify version if loaded")
    agent_version: Optional[str] = Field(None, description="CIRIS Agent version")
    hardware_type: Optional[str] = Field(None, description="Hardware security type")
    key_status: str = Field(..., description="Key status: 'none', 'ephemeral', 'portal_pending', 'portal_active'")
    key_id: Optional[str] = Field(None, description="Portal-issued key ID if activated")
    attestation_status: str = Field(..., description="Attestation: 'not_attempted', 'pending', 'verified', 'failed'")
    error: Optional[str] = Field(None, description="Error message if verify failed to load")
    diagnostic_info: Optional[str] = Field(None, description="Detailed diagnostic info")
    disclaimer: str = Field(
        default="CIRISVerify provides cryptographic attestation of agent identity and behavior. "
        "This enables participation in the Coherence Ratchet and CIRIS Scoring. "
        "CIRISVerify is REQUIRED for CIRIS 2.0 agents.",
        description="Trust and security disclaimer text",
    )
    # Attestation level checks
    dns_us_ok: bool = Field(default=False)
    dns_eu_ok: bool = Field(default=False)
    https_us_ok: bool = Field(default=False)
    https_eu_ok: bool = Field(default=False)
    binary_ok: bool = Field(default=False)
    file_integrity_ok: bool = Field(default=False)
    registry_ok: bool = Field(default=False)
    audit_ok: bool = Field(default=False)
    env_ok: bool = Field(default=False)
    play_integrity_ok: bool = Field(default=False)
    play_integrity_verdict: Optional[str] = Field(default=None)
    max_level: int = Field(default=0)
    attestation_mode: str = Field(default="partial")
    # Detailed info
    checks: Optional[Dict[str, Any]] = Field(default=None)
    details: Optional[Dict[str, Any]] = Field(default=None)
    platform_os: Optional[str] = Field(default=None)
    platform_arch: Optional[str] = Field(default=None)
    total_files: Optional[int] = Field(default=None)
    files_checked: Optional[int] = Field(default=None)
    files_passed: Optional[int] = Field(default=None)
    files_failed: Optional[int] = Field(default=None)
    integrity_failure_reason: Optional[str] = Field(default=None)
    function_integrity: Optional[str] = Field(default=None)
    source_errors: Optional[Dict[str, Dict[str, str]]] = Field(default=None)
    ed25519_fingerprint: Optional[str] = Field(default=None)
    key_storage_mode: Optional[str] = Field(default=None)
    hardware_backed: bool = Field(default=False)
    target_triple: Optional[str] = Field(default=None)
    binary_self_check: Optional[str] = Field(default=None)
    binary_hash: Optional[str] = Field(default=None)
    expected_binary_hash: Optional[str] = Field(default=None)
    function_self_check: Optional[str] = Field(default=None)
    functions_checked: Optional[int] = Field(default=None)
    functions_passed: Optional[int] = Field(default=None)
    registry_key_status: Optional[str] = Field(default=None)
    python_integrity_ok: bool = Field(default=False)
    python_modules_checked: Optional[int] = Field(default=None)
    python_modules_passed: Optional[int] = Field(default=None)
    python_total_hash: Optional[str] = Field(default=None)
    python_hash_valid: bool = Field(default=False)
    files_missing_count: Optional[int] = Field(default=None)
    files_missing_list: Optional[list[str]] = Field(default=None)
    files_failed_list: Optional[list[str]] = Field(default=None)
    files_unexpected_list: Optional[list[str]] = Field(default=None)
    functions_failed_list: Optional[list[str]] = Field(default=None)
    mobile_excluded_count: Optional[int] = Field(default=None)
    mobile_excluded_list: Optional[list[str]] = Field(default=None)
    sources_agreeing: int = Field(default=0)
    attestation_proof: Optional[Dict[str, Any]] = Field(default=None)
    per_file_results: Optional[Dict[str, str]] = Field(default=None)
    # Two-phase attestation
    level_pending: bool = Field(default=False)
    device_attestation: Optional[Dict[str, Any]] = Field(default=None)
    # Module integrity (v0.9.7)
    module_integrity_ok: bool = Field(default=False)
    module_integrity_summary: Optional[Dict[str, int]] = Field(default=None)

    # =========================================================================
    # CIRISVerify 1.2.x: Hardware Trust Detection
    # =========================================================================
    # THE KEY FLAG for wallet operations - when True, wallet is receive-only
    hardware_trust_degraded: bool = Field(
        default=False,
        description="True if hardware security is compromised (vulnerable SoC, rooted, emulator)",
    )
    trust_degradation_reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason for trust degradation",
    )
    # Hardware info
    soc_manufacturer: Optional[str] = Field(default=None, description="SoC manufacturer")
    soc_model: Optional[str] = Field(default=None, description="SoC model identifier")
    security_patch_level: Optional[str] = Field(default=None, description="Android security patch level")
    is_emulator: bool = Field(default=False, description="Device is an emulator")
    is_suspicious_emulator: bool = Field(default=False, description="Sophisticated emulator detected")
    bootloader_unlocked: Optional[bool] = Field(default=None, description="Bootloader unlocked")
    tee_implementation: Optional[str] = Field(default=None, description="TEE implementation type")
    is_rooted: bool = Field(default=False, description="Device is rooted")
    # Limitations and advisories (for UI display)
    hardware_limitations: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Why trust is degraded (limitation_type, advisory, etc.)"
    )
    security_advisories: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="CVE details for vulnerable hardware"
    )


class AppAttestVerifyRequest(BaseModel):
    """Request body for App Attest verification."""

    attestation: str = Field(..., description="Base64-encoded CBOR attestation")
    key_id: str = Field(..., description="Key ID from DCAppAttestService.generateKey()")
    nonce: str = Field(..., description="Nonce used when requesting the attestation")


class PlayIntegrityVerifyRequest(BaseModel):
    """Request body for Play Integrity verification."""

    token: str = Field(..., description="Play Integrity token from Google Play Services")
    nonce: str = Field(..., description="Nonce used when requesting the token")


class PlayIntegrityFailedRequest(BaseModel):
    """Request body for reporting Play Integrity failure."""

    error_code: int = Field(..., description="Error code from Play Integrity API (e.g., -16)")
    error_message: str = Field(..., description="Error message from Play Integrity API")


# ============================================================================
# Helpers
# ============================================================================


def _get_auth_service(request: Request) -> Any:
    """Get the authentication service from app state."""
    auth_service = getattr(request.app.state, "authentication_service", None)
    if auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service not available",
        )
    return auth_service


def _attestation_to_response(result: AttestationResult) -> VerifyStatusResponse:
    """Convert AttestationResult to VerifyStatusResponse.

    Both schemas are nearly identical, so this is mostly a direct mapping.
    """
    return VerifyStatusResponse(
        loaded=result.loaded,
        version=result.version,
        agent_version=result.agent_version,
        hardware_type=result.hardware_type,
        key_status=result.key_status,
        key_id=result.key_id,
        attestation_status=result.attestation_status,
        error=result.error,
        diagnostic_info=result.diagnostic_info,
        dns_us_ok=result.dns_us_ok,
        dns_eu_ok=result.dns_eu_ok,
        https_us_ok=result.https_us_ok,
        https_eu_ok=result.https_eu_ok,
        binary_ok=result.binary_ok,
        file_integrity_ok=result.file_integrity_ok,
        registry_ok=result.registry_ok,
        audit_ok=result.audit_ok,
        env_ok=result.env_ok,
        play_integrity_ok=result.play_integrity_ok,
        play_integrity_verdict=result.play_integrity_verdict,
        max_level=result.max_level,
        attestation_mode=result.attestation_mode,
        checks=result.checks,
        details=result.details,
        platform_os=result.platform_os,
        platform_arch=result.platform_arch,
        total_files=result.total_files,
        files_checked=result.files_checked,
        files_passed=result.files_passed,
        files_failed=result.files_failed,
        integrity_failure_reason=result.integrity_failure_reason,
        function_integrity=result.function_integrity,
        source_errors=result.source_errors,
        ed25519_fingerprint=result.ed25519_fingerprint,
        key_storage_mode=result.key_storage_mode,
        hardware_backed=result.hardware_backed,
        target_triple=result.target_triple,
        binary_self_check=result.binary_self_check,
        binary_hash=result.binary_hash,
        expected_binary_hash=result.expected_binary_hash,
        function_self_check=result.function_self_check,
        functions_checked=result.functions_checked,
        functions_passed=result.functions_passed,
        registry_key_status=result.registry_key_status,
        python_integrity_ok=result.python_integrity_ok,
        python_modules_checked=result.python_modules_checked,
        python_modules_passed=result.python_modules_passed,
        python_total_hash=result.python_total_hash,
        python_hash_valid=result.python_hash_valid,
        files_missing_count=result.files_missing_count,
        files_missing_list=result.files_missing_list,
        files_failed_list=result.files_failed_list,
        files_unexpected_list=result.files_unexpected_list,
        functions_failed_list=result.functions_failed_list,
        mobile_excluded_count=result.mobile_excluded_count,
        mobile_excluded_list=result.mobile_excluded_list,
        sources_agreeing=result.sources_agreeing,
        attestation_proof=result.attestation_proof,
        per_file_results=result.per_file_results,
        level_pending=result.level_pending,
        device_attestation=result.device_attestation,
        module_integrity_ok=result.module_integrity_ok,
        module_integrity_summary=result.module_integrity_summary,
        # CIRISVerify 1.2.x hardware trust fields
        hardware_trust_degraded=result.hardware_trust_degraded,
        trust_degradation_reason=result.trust_degradation_reason,
        soc_manufacturer=result.soc_manufacturer,
        soc_model=result.soc_model,
        security_patch_level=result.security_patch_level,
        is_emulator=result.is_emulator,
        is_suspicious_emulator=result.is_suspicious_emulator,
        bootloader_unlocked=result.bootloader_unlocked,
        tee_implementation=result.tee_implementation,
        is_rooted=result.is_rooted,
        hardware_limitations=result.hardware_limitations,
        security_advisories=result.security_advisories,
    )


def _get_verifier(request: Request) -> Any:
    """Get the CIRISVerify singleton via auth service."""
    auth_service = _get_auth_service(request)
    verifier = auth_service.get_verifier()
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=CIRISVERIFY_NOT_AVAILABLE,
        )
    return verifier


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/verify-status")
async def get_verify_status(
    request: Request,
    mode: str = "partial",
    play_integrity_token: Optional[str] = None,
    play_integrity_nonce: Optional[str] = None,
) -> SuccessResponse[VerifyStatusResponse]:
    """Get CIRISVerify status for Trust and Security display.

    Delegates to AuthenticationService.run_attestation() which handles:
    - CIRISVerify FFI calls with proper stack management
    - Caching with stale-while-revalidate
    - Play Integrity verification
    - File/function integrity checks

    This replaces the previous 1400-line inline implementation.

    Query Parameters:
    - mode: "full" for complete file integrity check, "partial" for spot-check
    - play_integrity_token: Optional Google Play Integrity token
    - play_integrity_nonce: Optional nonce used when requesting the token
    """
    auth_service = _get_auth_service(request)

    try:
        result = await auth_service.run_attestation(
            mode=mode,
            play_integrity_token=play_integrity_token,
            play_integrity_nonce=play_integrity_nonce,
        )
        return SuccessResponse(data=_attestation_to_response(result))
    except Exception as e:
        logger.error(f"[verify-status] Attestation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Attestation failed: {e}",
        )


@router.get("/attestation-status")
async def get_attestation_status(request: Request) -> SuccessResponse[Dict[str, Any]]:
    """Get cached attestation status without triggering a new check.

    Returns the current attestation cache status including:
    - Whether a cached result exists
    - Cache age and expiration status
    - Whether attestation is currently in progress
    - Max level from cached result (if available)
    """
    auth_service = _get_auth_service(request)

    cache_status = auth_service.get_attestation_cache_status()
    cached_result = auth_service.get_cached_attestation(allow_stale=True)

    return SuccessResponse(
        data={
            "has_cached_result": cache_status.has_cached_result,
            "cached_at": cache_status.cached_at.isoformat() if cache_status.cached_at else None,
            "cache_age_seconds": cache_status.cache_age_seconds,
            "cache_expired": cache_status.cache_expired,
            "attestation_in_progress": cache_status.attestation_in_progress,
            "max_level": cache_status.max_level,
            "has_stale_result": cache_status.has_stale_result,
            "stale_level": cache_status.stale_level,
            # Include summary from cached result if available
            "attestation_mode": cached_result.attestation_mode if cached_result else None,
            "play_integrity_ok": cached_result.play_integrity_ok if cached_result else False,
            "level_pending": cached_result.level_pending if cached_result else False,
        }
    )


@router.get("/app-attest/nonce")
async def get_app_attest_nonce(request: Request) -> SuccessResponse[Dict[str, Any]]:
    """Get a nonce for iOS App Attest verification.

    Calls CIRISVerify FFI -> registry GET /v1/integrity/ios/nonce.
    The iOS app uses this nonce as the challenge hash when calling
    DCAppAttestService.attestKey(_:clientDataHash:).
    """
    import ctypes
    import threading

    verifier = _get_verifier(request)

    def _get_nonce() -> dict[str, Any]:
        result: dict[str, Any] = {}

        def _inner() -> None:
            try:
                lib = verifier._lib
                if not lib or not hasattr(lib, "ciris_verify_get_app_attest_nonce"):
                    result["error"] = "App Attest FFI not available (need CIRISVerify >= 0.8.19)"
                    return

                lib.ciris_verify_get_app_attest_nonce.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(ctypes.c_size_t),
                ]
                lib.ciris_verify_get_app_attest_nonce.restype = ctypes.c_int

                handle = verifier._handle
                nonce_ptr = ctypes.c_void_p()
                nonce_len = ctypes.c_size_t()

                ret = lib.ciris_verify_get_app_attest_nonce(
                    handle,
                    ctypes.byref(nonce_ptr),
                    ctypes.byref(nonce_len),
                )

                if ret != 0:
                    result["error"] = f"FFI error code: {ret}"
                    return

                nonce_bytes = ctypes.string_at(nonce_ptr.value, nonce_len.value)  # type: ignore[arg-type]
                lib.ciris_verify_free(ctypes.cast(nonce_ptr, ctypes.c_char_p))
                result["data"] = json.loads(nonce_bytes.decode("utf-8"))
            except Exception as e:
                result["error"] = str(e)

        # Run on 8MB stack thread (CIRISVerify Rust runtime compatibility)
        threading.stack_size(8 * 1024 * 1024)
        t = threading.Thread(target=_inner)
        t.start()
        t.join(timeout=15)
        threading.stack_size(0)
        return result

    loop = asyncio.get_event_loop()
    ffi_result = await loop.run_in_executor(None, _get_nonce)

    if "error" in ffi_result:
        logger.warning(f"[app-attest] Nonce request failed: {ffi_result['error']}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ffi_result["error"],
        )

    return SuccessResponse(data=ffi_result["data"])


@router.post("/app-attest/verify")
async def verify_app_attest(
    request: Request,
    body: AppAttestVerifyRequest,
) -> SuccessResponse[Dict[str, Any]]:
    """Verify an iOS App Attest attestation object.

    Calls CIRISVerify FFI -> registry POST /v1/integrity/ios/verify.
    The registry verifies the CBOR attestation against Apple's certificate chain.
    """
    import ctypes
    import threading

    verifier = _get_verifier(request)

    def _verify() -> dict[str, Any]:
        result: dict[str, Any] = {}

        def _inner() -> None:
            try:
                lib = verifier._lib
                if not lib or not hasattr(lib, "ciris_verify_app_attest"):
                    result["error"] = "App Attest FFI not available (need CIRISVerify >= 0.8.19)"
                    return

                lib.ciris_verify_app_attest.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_char_p,
                    ctypes.c_size_t,
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(ctypes.c_size_t),
                ]
                lib.ciris_verify_app_attest.restype = ctypes.c_int

                request_json = json.dumps(
                    {
                        "attestation": body.attestation,
                        "key_id": body.key_id,
                        "nonce": body.nonce,
                    }
                ).encode("utf-8")

                handle = verifier._handle
                response_ptr = ctypes.c_void_p()
                response_len = ctypes.c_size_t()

                ret = lib.ciris_verify_app_attest(
                    handle,
                    request_json,
                    len(request_json),
                    ctypes.byref(response_ptr),
                    ctypes.byref(response_len),
                )

                if ret != 0:
                    result["error"] = f"FFI error code: {ret}"
                    return

                response_bytes = ctypes.string_at(response_ptr.value, response_len.value)  # type: ignore[arg-type]
                lib.ciris_verify_free(ctypes.cast(response_ptr, ctypes.c_char_p))
                result["data"] = json.loads(response_bytes.decode("utf-8"))
            except Exception as e:
                result["error"] = str(e)

        threading.stack_size(8 * 1024 * 1024)
        t = threading.Thread(target=_inner)
        t.start()
        t.join(timeout=30)
        threading.stack_size(0)
        return result

    loop = asyncio.get_event_loop()
    ffi_result = await loop.run_in_executor(None, _verify)

    if "error" in ffi_result:
        logger.warning(f"[app-attest] Verification failed: {ffi_result['error']}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ffi_result["error"],
        )

    # Device attestation succeeded — invalidate attestation cache and re-run
    # so the level recalculates with the device attestation data included.
    verified = ffi_result.get("data", {}).get("verified", False)
    if verified:
        logger.info("[app-attest] Device attestation verified, invalidating cache and re-running attestation")
        try:
            auth_service = _get_auth_service(request)
            auth_service.invalidate_attestation_cache()
            # Background re-attestation - track task to prevent GC
            task = asyncio.create_task(auth_service.run_startup_attestation())
            if hasattr(auth_service, "_background_tasks"):
                auth_service._background_tasks.add(task)
                task.add_done_callback(auth_service._background_tasks.discard)
        except Exception as e:
            logger.warning(f"[app-attest] Failed to trigger re-attestation: {e}")

    return SuccessResponse(data=ffi_result["data"])


@router.get("/play-integrity/nonce")
async def get_play_integrity_nonce(request: Request) -> SuccessResponse[Dict[str, Any]]:
    """Get a nonce for Google Play Integrity verification.

    Calls CIRISVerify FFI -> registry GET /v1/integrity/android/nonce.
    The Android app uses this nonce when requesting a Play Integrity token.
    """
    import ctypes
    import threading

    verifier = _get_verifier(request)

    def _get_nonce() -> dict[str, Any]:
        result: dict[str, Any] = {}

        def _inner() -> None:
            try:
                lib = verifier._lib
                if not lib or not hasattr(lib, "ciris_verify_get_integrity_nonce"):
                    result["error"] = "Play Integrity FFI not available (need CIRISVerify >= 1.0.0)"
                    return

                lib.ciris_verify_get_integrity_nonce.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(ctypes.c_size_t),
                ]
                lib.ciris_verify_get_integrity_nonce.restype = ctypes.c_int

                handle = verifier._handle
                nonce_ptr = ctypes.c_void_p()
                nonce_len = ctypes.c_size_t()

                ret = lib.ciris_verify_get_integrity_nonce(
                    handle,
                    ctypes.byref(nonce_ptr),
                    ctypes.byref(nonce_len),
                )

                if ret != 0:
                    result["error"] = f"FFI error code: {ret}"
                    return

                nonce_bytes = ctypes.string_at(nonce_ptr.value, nonce_len.value)  # type: ignore[arg-type]
                lib.ciris_verify_free(ctypes.cast(nonce_ptr, ctypes.c_char_p))
                result["data"] = json.loads(nonce_bytes.decode("utf-8"))
            except Exception as e:
                result["error"] = str(e)

        threading.stack_size(8 * 1024 * 1024)
        t = threading.Thread(target=_inner)
        t.start()
        t.join(timeout=15)
        threading.stack_size(0)
        return result

    loop = asyncio.get_event_loop()
    ffi_result = await loop.run_in_executor(None, _get_nonce)

    if "error" in ffi_result:
        logger.warning(f"[play-integrity] Nonce request failed: {ffi_result['error']}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ffi_result["error"],
        )

    return SuccessResponse(data=ffi_result["data"])


@router.post("/play-integrity/verify")
async def verify_play_integrity(
    request: Request,
    body: PlayIntegrityVerifyRequest,
) -> SuccessResponse[Dict[str, Any]]:
    """Verify a Google Play Integrity token.

    Delegates to AuthenticationService.verify_play_integrity_token() which:
    - Calls CIRISVerify FFI with crash protection
    - Runs on 8MB stack thread for Rust/Tokio compatibility
    - Returns verification result with verdict details
    """
    auth_service = _get_auth_service(request)

    try:
        result = await auth_service.verify_play_integrity_token(
            token=body.token,
            nonce=body.nonce,
        )

        verified = result.get("verified", False)
        verdict = result.get("verdict", "UNKNOWN")

        return SuccessResponse(
            data={
                "verified": verified,
                "verdict": verdict,
                "device_verdict": verdict,
                "meets_strong_integrity": result.get("meets_strong_integrity", False),
                "meets_device_integrity": result.get("meets_device_integrity", False),
                "meets_basic_integrity": result.get("meets_basic_integrity", False),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[play-integrity] Verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Play Integrity verification failed: {e}",
        )


@router.post("/play-integrity/failed")
async def report_play_integrity_failed(
    request: Request,
    body: PlayIntegrityFailedRequest,
) -> SuccessResponse[Dict[str, Any]]:
    """Report Play Integrity token acquisition failure.

    Called when the Android app fails to get a Play Integrity token
    (e.g., error -16 CLOUD_PROJECT_NUMBER_INVALID). This allows CIRISVerify
    to mark device attestation as failed (not pending) so level_pending=false.

    Added in CIRISVerify 1.5.3.
    """
    verifier = _get_verifier(request)

    # Check if FFI supports this (>= 1.5.3)
    if not verifier.has_device_attestation_failed_support:
        logger.warning("[play-integrity] device_attestation_failed not available (need >= 1.5.3)")
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="device_attestation_failed requires CIRISVerify >= 1.5.3",
        )

    try:
        await verifier.device_attestation_failed(
            platform="android",
            error_code=body.error_code,
            error_message=body.error_message,
        )
        logger.info(f"[play-integrity] Reported failure: code={body.error_code}, msg={body.error_message}")

        # Invalidate cache and re-run attestation with device_attestation marked as failed
        auth_service = _get_auth_service(request)
        auth_service.invalidate_attestation_cache()
        task = asyncio.create_task(auth_service.run_startup_attestation())
        if hasattr(auth_service, "_background_tasks"):
            auth_service._background_tasks.add(task)
            task.add_done_callback(auth_service._background_tasks.discard)

        return SuccessResponse(
            data={
                "reported": True,
                "error_code": body.error_code,
                "message": "Device attestation failure recorded, level_pending will be false",
            }
        )
    except Exception as e:
        logger.error(f"[play-integrity] Failed to report failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to report Play Integrity failure: {e}",
        )
