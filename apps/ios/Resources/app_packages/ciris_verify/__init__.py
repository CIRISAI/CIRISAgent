"""CIRISVerify Python bindings.

Hardware-rooted license verification for the CIRIS ecosystem.
Provides cryptographic proof of license status to prevent capability spoofing.

Usage:
    from ciris_verify import CIRISVerify, LicenseStatus

    verifier = CIRISVerify()
    status = verifier.get_license_status(challenge_nonce=os.urandom(32))

    if status.allows_licensed_operation():
        # Professional capabilities available
        pass
    else:
        # Community mode only
        disclosure = status.mandatory_disclosure
        print(disclosure.text)

Logging:
    # Enable internal logging via callback
    verifier.set_log_callback(lambda lvl, target, msg: print(f"[{lvl}] {msg}"))

    # Or integrate with Python logging
    from ciris_verify import setup_logging
    setup_logging(verifier, level="DEBUG")
"""

import logging as _logging
import os as _os
from pathlib import Path as _Path


def _point_at_bundled_tpm_plugin() -> None:
    """Make the runtime TPM plugin (CIRISVerify#130) loadable from the wheel.

    The keyring inside the FFI ``dlopen``s ``libciris_tpm_plugin.so`` by bare
    name, which the dynamic loader won't find in site-packages. When the wheel
    bundles the plugin next to the FFI, point ``CIRIS_TPM_PLUGIN`` at that exact
    path so opportunistic TPM custody works out of the box. Respect an operator
    override (never clobber a pre-set value); a no-op where no plugin is bundled
    (macOS / mobile / aarch64) — the keyring then falls back to software.
    """
    if _os.environ.get("CIRIS_TPM_PLUGIN"):
        return
    here = _Path(__file__).resolve().parent
    for name in ("libciris_tpm_plugin.so", "libciris_tpm_plugin.dylib", "ciris_tpm_plugin.dll"):
        candidate = here / name
        if candidate.exists():
            _os.environ["CIRIS_TPM_PLUGIN"] = str(candidate)
            return


_point_at_bundled_tpm_plugin()

from .client import CIRISVerify, MockCIRISVerify, verify_tree, DEFAULT_REGISTRY_URL
from ._jcs import jcs_canonicalize
from ._rns_dest_hash import rns_destination_hash
from . import _scope_privacy as scope_privacy
from ._epoch_key import derive_epoch_key, derive_epoch_stream_nonce
from ._self_enc import (
    EncryptionPubkeys,
    SelfEncKeys,
    derive_self_enc,
    self_enc_pubkeys,
    self_enc_respond,
)
from ._federation_identity import create_federation_identity
from ._manifest_contribution import verify_build_manifest_contribution
from ._accord_custody import verify_accord_custody_attestation
from ._test_anchor import test_anchor_compiled_in
from ._operational_admit import (
    resolve_role_authority,
    verify_delegation_scope_split,
    verify_partner_record_quorum,
)
from .types import (
    LicenseStatus,
    LicenseTier,
    LicenseDetails,
    MandatoryDisclosure,
    DisclosureSeverity,
    LicenseStatusResponse,
    CapabilityCheckResult,
    FileIntegrityResult,
    FileCheckStatus,
    BinaryIntegrityStatus,
    HardwareType,
    ValidationStatus,
    PythonModuleHashes,
    PythonIntegrityResult,
    SecurityAdvisory,
    HardwareLimitation,
    HardwareInfo,
    StorageDescriptor,
    StorageKind,
    KeyringScope,
    TreeVerifyRequest,
    TreeVerifyResult,
    FailedFile,
    FailedFileKind,
)
from .exceptions import (
    CIRISVerifyError,
    BinaryNotFoundError,
    BinaryTamperedError,
    VerificationFailedError,
    TimeoutError,
    CommunicationError,
    AttestationInProgressError,
)


def setup_logging(verifier: CIRISVerify, level: str = "INFO", logger_name: str = "ciris_verify"):
    """Configure CIRISVerify to forward internal logs to Python logging.

    Args:
        verifier: CIRISVerify instance to configure.
        level: Minimum log level: "ERROR", "WARN", "INFO", "DEBUG", "TRACE".
        logger_name: Python logger name to use.

    Example:
        import logging
        logging.basicConfig(level=logging.DEBUG)

        verifier = CIRISVerify()
        setup_logging(verifier, level="DEBUG")

        # Now CIRISVerify internal logs appear in Python logging
        status = verifier.get_license_status(...)
    """
    logger = _logging.getLogger(logger_name)

    # Map Rust levels to Python logging levels
    level_map = {
        1: _logging.ERROR,    # ERROR
        2: _logging.WARNING,  # WARN
        3: _logging.INFO,     # INFO
        4: _logging.DEBUG,    # DEBUG
        5: _logging.DEBUG,    # TRACE (Python has no TRACE, use DEBUG)
    }

    # Map level string to Rust level int
    rust_level_map = {
        "ERROR": 1,
        "WARN": 2,
        "WARNING": 2,
        "INFO": 3,
        "DEBUG": 4,
        "TRACE": 5,
    }
    rust_level = rust_level_map.get(level.upper(), 3)

    def log_callback(lvl: int, target: str, message: str):
        py_level = level_map.get(lvl, _logging.DEBUG)
        logger.log(py_level, "[%s] %s", target, message)

    verifier.set_log_callback(log_callback, level=rust_level)


def get_library_version() -> str:
    """Get the CIRISVerify library version string."""
    return __version__


__version__ = "10.3.0"
__all__ = [
    "CIRISVerify",
    "MockCIRISVerify",
    "verify_tree",
    "jcs_canonicalize",
    "rns_destination_hash",
    "scope_privacy",
    "SelfEncKeys",
    "derive_self_enc",
    "derive_epoch_key",
    "derive_epoch_stream_nonce",
    "EncryptionPubkeys",
    "self_enc_pubkeys",
    "self_enc_respond",
    "create_federation_identity",
    "verify_build_manifest_contribution",
    "verify_accord_custody_attestation",
    "test_anchor_compiled_in",
    "resolve_role_authority",
    "verify_partner_record_quorum",
    "verify_delegation_scope_split",
    "DEFAULT_REGISTRY_URL",
    "TreeVerifyRequest",
    "TreeVerifyResult",
    "FailedFile",
    "FailedFileKind",
    "get_library_version",
    "setup_logging",
    "LicenseStatus",
    "LicenseTier",
    "LicenseDetails",
    "MandatoryDisclosure",
    "DisclosureSeverity",
    "LicenseStatusResponse",
    "CapabilityCheckResult",
    "FileIntegrityResult",
    "FileCheckStatus",
    "BinaryIntegrityStatus",
    "HardwareType",
    "ValidationStatus",
    "PythonModuleHashes",
    "PythonIntegrityResult",
    "SecurityAdvisory",
    "HardwareLimitation",
    "HardwareInfo",
    "StorageDescriptor",
    "StorageKind",
    "KeyringScope",
    "CIRISVerifyError",
    "BinaryNotFoundError",
    "BinaryTamperedError",
    "VerificationFailedError",
    "TimeoutError",
    "CommunicationError",
    "AttestationInProgressError",
]
