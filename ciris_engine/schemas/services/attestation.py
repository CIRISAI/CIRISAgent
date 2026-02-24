"""Attestation schemas for CIRISVerify integration.

These schemas define the structure for agent attestation and code integrity verification.
CIRISVerify is REQUIRED for CIRIS 2.0+ agents.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AttestationResult(BaseModel):
    """Result of a full attestation check.

    This is the cached result stored in AuthenticationService.
    """

    # Core status
    loaded: bool = Field(..., description="Whether CIRISVerify library is loaded")
    version: Optional[str] = Field(None, description="CIRISVerify version if loaded")
    hardware_type: Optional[str] = Field(None, description="Hardware security type (TPM_2_0, SOFTWARE_ONLY, etc.)")
    key_status: str = Field(..., description="Key status: 'none', 'ephemeral', 'portal_pending', 'portal_active'")
    key_id: Optional[str] = Field(None, description="Portal-issued key ID if activated")
    attestation_status: str = Field(..., description="Attestation: 'not_attempted', 'pending', 'verified', 'failed'")
    error: Optional[str] = Field(None, description="Error message if verify failed to load")
    diagnostic_info: Optional[str] = Field(None, description="Detailed diagnostic info for troubleshooting")

    # Attestation level checks
    dns_us_ok: bool = Field(default=False, description="CIRIS DNS connectivity (US)")
    dns_eu_ok: bool = Field(default=False, description="CIRIS DNS connectivity (EU)")
    https_us_ok: bool = Field(default=False, description="CIRIS HTTPS connectivity (US)")
    https_eu_ok: bool = Field(default=False, description="CIRIS HTTPS connectivity (EU)")
    binary_ok: bool = Field(default=False, description="CIRISVerify binary loaded and functional")
    file_integrity_ok: bool = Field(default=False, description="File integrity verified (Tripwire-style)")
    registry_ok: bool = Field(default=False, description="Signing key registered with Portal/Registry")
    audit_ok: bool = Field(default=False, description="Audit trail intact")
    env_ok: bool = Field(default=False, description="Environment (.env) properly configured")
    play_integrity_ok: bool = Field(default=False, description="Google Play Integrity verification passed")
    play_integrity_verdict: Optional[str] = Field(
        default=None, description="Play Integrity verdict (MEETS_STRONG_INTEGRITY, etc.)"
    )
    max_level: int = Field(default=0, description="Maximum attestation level achieved (0-5)")

    # Attestation mode
    attestation_mode: str = Field(default="partial", description="Attestation mode: 'full' or 'partial'")

    # Detailed attestation info (for expanded view)
    checks: Optional[Dict[str, Any]] = Field(default=None, description="Per-check details with ok/label/level")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Full attestation details from CIRISVerify")

    # Platform info from attestation
    platform_os: Optional[str] = Field(default=None, description="Platform OS from attestation")
    platform_arch: Optional[str] = Field(default=None, description="Platform architecture")

    # Integrity details
    total_files: Optional[int] = Field(default=None, description="Total files in registry manifest")
    files_checked: Optional[int] = Field(default=None, description="Number of files checked for integrity")
    files_passed: Optional[int] = Field(default=None, description="Number of files that passed integrity")
    files_failed: Optional[int] = Field(default=None, description="Number of files that failed integrity")
    integrity_failure_reason: Optional[str] = Field(default=None, description="Reason for integrity failure if any")

    # v0.6.0: Function integrity verification (constructor-based)
    function_integrity: Optional[str] = Field(
        default=None,
        description="Function integrity: verified, tampered, unavailable:{reason}, signature_invalid, not_found, pending",
    )

    # v0.6.0: Per-source error details for network validation
    source_errors: Optional[Dict[str, Dict[str, str]]] = Field(
        default=None, description="Per-source error details: {source: {category: str, details: str}}"
    )

    # v0.7.0: Enhanced verification details
    ed25519_fingerprint: Optional[str] = Field(default=None, description="Ed25519 public key fingerprint (SHA-256 hex)")
    key_storage_mode: Optional[str] = Field(
        default=None, description="Key storage mode: SOFTWARE, HARDWARE_BACKED, or specific provider"
    )
    hardware_backed: bool = Field(default=False, description="Whether the key is hardware-backed")
    target_triple: Optional[str] = Field(
        default=None, description="Target triple being checked against registry (e.g., aarch64-linux-android)"
    )
    binary_self_check: Optional[str] = Field(
        default=None, description="Binary self-check status: verified, mismatch, not_found, unavailable:{reason}"
    )
    binary_hash: Optional[str] = Field(default=None, description="Binary hash computed locally")
    expected_binary_hash: Optional[str] = Field(default=None, description="Expected binary hash from registry")
    function_self_check: Optional[str] = Field(
        default=None, description="Function self-check status: verified, mismatch, not_found, unavailable:{reason}"
    )
    functions_checked: Optional[int] = Field(default=None, description="Number of functions verified")
    functions_passed: Optional[int] = Field(default=None, description="Number of functions that passed verification")
    registry_key_status: Optional[str] = Field(default=None, description="Registry key verification status")

    # v0.8.1: Python integrity for mobile
    python_integrity_ok: bool = Field(default=False, description="Python module integrity verified")
    python_modules_checked: Optional[int] = Field(default=None, description="Number of Python modules checked")
    python_modules_passed: Optional[int] = Field(default=None, description="Number of Python modules that passed")
    python_total_hash: Optional[str] = Field(default=None, description="Total hash of all Python modules")
    python_hash_valid: bool = Field(default=False, description="Whether Python total hash matches expected")

    # v0.8.4: Enhanced detail lists for UI
    files_missing_count: Optional[int] = Field(default=None, description="Number of manifest files not on device")
    files_missing_list: Optional[List[str]] = Field(default=None, description="List of missing files (max 50)")
    files_failed_list: Optional[List[str]] = Field(
        default=None, description="List of files that failed hash check (max 50)"
    )
    files_unexpected_list: Optional[List[str]] = Field(default=None, description="List of unexpected files (max 50)")
    functions_failed_list: Optional[List[str]] = Field(
        default=None, description="List of functions that failed verification (max 50)"
    )

    # v0.8.6: Mobile exclusion tracking for correct denominator
    mobile_excluded_count: Optional[int] = Field(
        default=None, description="Files excluded from mobile (discord, reddit, cli, etc.)"
    )
    mobile_excluded_list: Optional[List[str]] = Field(
        default=None, description="List of mobile-excluded files (max 50)"
    )

    # v0.8.5: Registry sources agreement and attestation proof
    sources_agreeing: int = Field(default=0, description="Number of registry sources that agree (0-3)")
    attestation_proof: Optional[Dict[str, Any]] = Field(
        default=None, description="Full attestation proof from CIRISVerify"
    )

    # v0.8.6: Per-file results for deconflicted integrity display
    per_file_results: Optional[Dict[str, str]] = Field(
        default=None, description="Per-file status map (path -> passed/failed/missing/unreadable)"
    )

    # Cache metadata
    cached_at: Optional[datetime] = Field(default=None, description="When this result was cached")
    cache_ttl_seconds: int = Field(default=300, description="Cache TTL in seconds (default 5 minutes)")


class AttestationCacheStatus(BaseModel):
    """Status of the attestation cache."""

    has_cached_result: bool = Field(..., description="Whether a cached result exists")
    cached_at: Optional[datetime] = Field(None, description="When the result was cached")
    cache_age_seconds: Optional[float] = Field(None, description="Age of cache in seconds")
    cache_expired: bool = Field(default=False, description="Whether cache has expired")
    attestation_in_progress: bool = Field(default=False, description="Whether attestation is currently running")
    max_level: Optional[int] = Field(None, description="Cached max attestation level (0-5)")


class AttestationRequest(BaseModel):
    """Request to run attestation."""

    mode: str = Field(default="partial", description="Attestation mode: 'full' or 'partial'")
    play_integrity_token: Optional[str] = Field(None, description="Google Play Integrity token")
    play_integrity_nonce: Optional[str] = Field(None, description="Nonce used for Play Integrity request")
    force_refresh: bool = Field(default=False, description="Force refresh even if cache is valid")
