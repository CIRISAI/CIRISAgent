"""Result builder for attestation.

This module builds AttestationResult from raw CIRISVerify response data.
"""

import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic.utils.mobile_exclusions import (
    compute_files_missing_list,
    compute_files_unexpected_list,
    compute_mobile_excluded_count,
    compute_mobile_excluded_list,
)
from ciris_engine.schemas.services.attestation import AttestationResult

from .types import VerifyThreadResult

logger = logging.getLogger(__name__)


def _extract_sources(attestation: Dict[str, Any]) -> Dict[str, Any]:
    """Extract sources section from attestation data."""
    return attestation.get("sources", {}) or {}


def _extract_key_attestation(attestation: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key attestation section from attestation data."""
    return attestation.get("key_attestation", {}) or {}


def _extract_file_integrity(attestation: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize file integrity section.

    The file_integrity response may be nested under 'full' key.
    """
    file_integrity_raw = attestation.get("file_integrity") or {}
    if isinstance(file_integrity_raw, dict):
        result = file_integrity_raw.get("full", file_integrity_raw)
        return result if isinstance(result, dict) else {}
    return {}


def _extract_module_integrity(attestation: Dict[str, Any]) -> Dict[str, Any]:
    """Extract module integrity section (v0.9.7+)."""
    module_integrity = attestation.get("module_integrity") or {}
    if module_integrity:
        logger.info(f"[attestation] module_integrity keys: {list(module_integrity.keys())}")
        summary = module_integrity.get("summary")
        if summary:
            logger.info(f"[attestation] module_integrity summary: {summary}")
        # Debug: show list sizes
        cv_list = module_integrity.get("cross_validated", [])
        fs_list = module_integrity.get("filesystem_verified", [])
        av_list = module_integrity.get("agent_verified", [])
        logger.info(
            f"[attestation] cross_validated count={len(cv_list)}, "
            f"filesystem_verified count={len(fs_list)}, "
            f"agent_verified count={len(av_list)}"
        )
    return module_integrity


def _count_agreeing_sources(sources: Dict[str, Any]) -> int:
    """Count number of agreeing DNS/HTTPS sources."""
    return sum(
        [
            sources.get("dns_us_valid", False),
            sources.get("dns_eu_valid", False),
            sources.get("https_valid", False),
        ]
    )


def _build_file_integrity_fields(
    file_integrity: Dict[str, Any],
    level: int,
) -> Dict[str, Any]:
    """Build file integrity related fields for AttestationResult."""
    if not file_integrity:
        return {
            "file_integrity_ok": level >= 4,
            "total_files": None,
            "files_checked": None,
            "files_passed": None,
            "files_failed": None,
            "per_file_results": None,
            "files_missing_count": None,
            "files_missing_list": None,
            "files_failed_list": None,
            "files_unexpected_list": None,
            "mobile_excluded_count": None,
            "mobile_excluded_list": None,
        }

    per_file_results = file_integrity.get("per_file_results")

    # Get unexpected files directly from file_integrity response (preferred)
    # Falls back to computing from per_file_results if not available
    unexpected_files = file_integrity.get("unexpected_files")
    if unexpected_files is None and per_file_results:
        unexpected_files = compute_files_unexpected_list(per_file_results)

    return {
        "file_integrity_ok": file_integrity.get("valid", False),
        "total_files": file_integrity.get("total_files"),
        "files_checked": file_integrity.get("files_checked"),
        "files_passed": file_integrity.get("files_passed"),
        "files_failed": file_integrity.get("files_failed"),
        "per_file_results": per_file_results,
        "files_missing_count": file_integrity.get("files_missing_count"),
        "files_missing_list": compute_files_missing_list(per_file_results) if per_file_results else None,
        "files_failed_list": file_integrity.get("files_failed_list"),
        "files_unexpected_list": unexpected_files,
        "mobile_excluded_count": compute_mobile_excluded_count(per_file_results) if per_file_results else None,
        "mobile_excluded_list": compute_mobile_excluded_list(per_file_results) if per_file_results else None,
    }


def _build_python_integrity_fields(python_integrity: Dict[str, Any]) -> Dict[str, Any]:
    """Build Python integrity related fields for AttestationResult."""
    if not python_integrity:
        return {
            "python_integrity_ok": False,
            "python_modules_checked": None,
            "python_modules_passed": None,
            "python_modules_failed": None,
            "python_total_hash": None,
            "python_hash_valid": False,
            "python_failed_modules": None,
        }

    return {
        "python_integrity_ok": python_integrity.get("valid", False),
        "python_modules_checked": python_integrity.get("modules_checked"),
        "python_modules_passed": python_integrity.get("modules_passed"),
        "python_modules_failed": python_integrity.get("modules_failed"),
        "python_total_hash": python_integrity.get("actual_total_hash"),
        "python_hash_valid": python_integrity.get("total_hash_valid", False),
        "python_failed_modules": python_integrity.get("failed_modules"),
    }


def _build_module_integrity_fields(module_integrity: Dict[str, Any]) -> Dict[str, Any]:
    """Build module integrity related fields for AttestationResult (v0.9.7+)."""
    if not module_integrity:
        return {
            "module_integrity_ok": False,
            "module_integrity_summary": None,
            "cross_validated_files": None,
            "filesystem_verified_files": None,
            "agent_verified_files": None,
            "disk_agent_mismatch": None,
            "registry_mismatch_files": None,
        }

    return {
        "module_integrity_ok": module_integrity.get("valid", False),
        "module_integrity_summary": module_integrity.get("summary"),
        "cross_validated_files": module_integrity.get("cross_validated", [])[:50],
        "filesystem_verified_files": module_integrity.get("filesystem_verified", [])[:50],
        "agent_verified_files": module_integrity.get("agent_verified", [])[:50],
        "disk_agent_mismatch": module_integrity.get("disk_agent_mismatch"),
        "registry_mismatch_files": module_integrity.get("registry_mismatch"),
    }


def _build_self_verification_fields(
    self_verification: Dict[str, Any],
    python_integrity: Dict[str, Any],
) -> Dict[str, Any]:
    """Build self-verification related fields for AttestationResult."""
    # Use explicit None check - 0 is valid and should NOT fall through to python_integrity
    functions_checked = self_verification.get("functions_checked")
    if functions_checked is None:
        functions_checked = python_integrity.get("modules_checked")

    functions_passed = self_verification.get("functions_passed")
    if functions_passed is None:
        functions_passed = python_integrity.get("modules_passed")

    return {
        "binary_self_check": "verified" if self_verification.get("binary_valid") else "failed",
        "binary_hash": self_verification.get("binary_hash"),
        "function_self_check": "verified" if self_verification.get("functions_valid") else "failed",
        "functions_checked": functions_checked,
        "functions_passed": functions_passed,
        "functions_failed_list": self_verification.get("functions_failed_list"),
        "function_integrity": "verified" if self_verification.get("functions_valid") else "failed",
        "target_triple": self_verification.get("target"),
    }


def _log_diagnostic_info(data: Dict[str, Any], attestation: Dict[str, Any]) -> None:
    """Log diagnostic information for debugging."""
    logger.info(f"[attestation] DIAGNOSTIC: verify_result[0] keys: {list(data.keys()) if data else 'None'}")
    logger.info(f"[attestation] DIAGNOSTIC: attestation keys: {list(attestation.keys()) if attestation else 'None'}")
    if attestation:
        logger.info(
            f"[attestation] DIAGNOSTIC: level={attestation.get('level')}, "
            f"valid={attestation.get('valid')}, level_pending={attestation.get('level_pending')}"
        )
        logger.info(f"[attestation] DIAGNOSTIC: python_integrity={attestation.get('python_integrity')}")
        logger.info(f"[attestation] DIAGNOSTIC: file_integrity={attestation.get('file_integrity')}")
        logger.info(f"[attestation] DIAGNOSTIC: self_verification={attestation.get('self_verification')}")
        logger.info(f"[attestation] DIAGNOSTIC: error={attestation.get('error')}")


def build_attestation_result(
    verify_result: VerifyThreadResult,
    attestation_mode: str,
) -> AttestationResult:
    """Build AttestationResult from verification thread result.

    Args:
        verify_result: Result from verification thread
        attestation_mode: "full" or "partial"

    Returns:
        AttestationResult populated from verification data
    """
    # Handle errors
    if verify_result.error:
        logger.info(f"[attestation] DIAGNOSTIC: Early return due to error: {verify_result.error}")
        return AttestationResult(
            loaded=False,
            key_status="none",
            attestation_status="failed",
            error=verify_result.error,
            attestation_mode=attestation_mode,
        )

    # Parse attestation data
    data = verify_result.result or {}
    attestation = data.get("attestation", {}) or {}

    _log_diagnostic_info(data, attestation)

    # Extract sub-sections
    sources = _extract_sources(attestation)
    key_attestation = _extract_key_attestation(attestation)
    file_integrity = _extract_file_integrity(attestation)
    module_integrity = _extract_module_integrity(attestation)
    audit_trail = attestation.get("audit_trail") or {}
    python_integrity = attestation.get("python_integrity") or {}
    self_verification = attestation.get("self_verification") or {}
    device_attestation = attestation.get("device_attestation") or {}

    logger.info(f"[attestation] DIAGNOSTIC: device_attestation={device_attestation}")

    level = attestation.get("level", 0)

    # Build field groups
    file_fields = _build_file_integrity_fields(file_integrity, level)
    python_fields = _build_python_integrity_fields(python_integrity)
    module_fields = _build_module_integrity_fields(module_integrity)
    self_verify_fields = _build_self_verification_fields(self_verification, python_integrity)

    return AttestationResult(
        loaded=True,
        version=data.get("version") or self_verification.get("binary_version"),
        hardware_type=key_attestation.get("hardware_type") or attestation.get("hardware_type"),
        key_status=key_attestation.get("key_type", "none"),
        key_id=key_attestation.get("key_id"),
        attestation_status="verified" if attestation.get("valid") else "partial",
        attestation_mode=attestation_mode,
        # Level from run_attestation_sync
        max_level=level,
        # Source validation (Level 3)
        dns_us_ok=sources.get("dns_us_valid", False),
        dns_eu_ok=sources.get("dns_eu_valid", False),
        https_us_ok=sources.get("https_valid", False),
        https_eu_ok=sources.get("https_valid", False),
        # Binary/key attestation (Level 1-2)
        binary_ok=self_verification.get("binary_valid", False),
        env_ok=not key_attestation.get("running_in_vm", False),
        # Registry validation (Level 3)
        registry_ok=key_attestation.get("registry_key_status") == "active",
        registry_key_status=key_attestation.get("registry_key_status") or attestation.get("registry_key_status"),
        sources_agreeing=_count_agreeing_sources(sources),
        # File integrity (Level 4)
        **file_fields,
        # Audit trail (Level 5)
        audit_ok=audit_trail.get("valid", False) if audit_trail else False,
        # Play/Device Integrity
        play_integrity_ok=device_attestation.get("verified", False),
        play_integrity_verdict=device_attestation.get("verdict"),
        # Two-phase attestation support
        level_pending=attestation.get("level_pending", False),
        device_attestation=device_attestation if device_attestation else None,
        # Python integrity
        **python_fields,
        # Module integrity (v0.9.7+)
        **module_fields,
        # Self-verification
        **self_verify_fields,
        # Key info
        ed25519_fingerprint=key_attestation.get("ed25519_fingerprint"),
        key_storage_mode=key_attestation.get("storage_mode"),
        hardware_backed=key_attestation.get("hardware_backed", False),
        # Full details
        details=attestation,
        attestation_proof=attestation.get("proof"),
    )
