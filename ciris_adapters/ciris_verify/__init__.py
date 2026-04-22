"""CIRISVerify adapter package.

This adapter integrates CIRISVerify license verification into the CIRIS agent.
The FFI bindings are bundled in the ffi_bindings subpackage.

Usage:
    from ciris_adapters.ciris_verify import CIRISVerifyAdapter

    adapter = CIRISVerifyAdapter(runtime, context)
    await adapter.start()
"""

# Export adapter-specific classes
from .adapter import CIRISVerifyAdapter  # noqa: F401

# Import from bundled FFI bindings
from .ffi_bindings import (  # noqa: F401
    AttestationInProgressError,
    BinaryIntegrityStatus,
    BinaryNotFoundError,
    BinaryTamperedError,
    CapabilityCheckResult,
    CIRISVerify,
    CIRISVerifyError,
    CommunicationError,
    DisclosureSeverity,
    FileCheckStatus,
    FileIntegrityResult,
    HardwareType,
    LicenseDetails,
    LicenseStatus,
    LicenseStatusResponse,
    LicenseTier,
    MandatoryDisclosure,
    PythonIntegrityResult,
    PythonModuleHashes,
    TimeoutError,
    ValidationStatus,
    VerificationFailedError,
    get_library_version,
    setup_logging,
)
from .service import CIRISVerifyService, VerificationConfig  # noqa: F401

# Alias for adapter loading code (looks for 'Adapter' class)
Adapter = CIRISVerifyAdapter

# Version from FFI bindings
from .ffi_bindings import __version__

__all__ = [
    # Adapter exports
    "Adapter",
    "CIRISVerifyAdapter",
    "CIRISVerifyService",
    "VerificationConfig",
    # Re-exports from FFI bindings
    "CIRISVerify",
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
    "CIRISVerifyError",
    "BinaryNotFoundError",
    "BinaryTamperedError",
    "VerificationFailedError",
    "TimeoutError",
    "CommunicationError",
    "AttestationInProgressError",
]
