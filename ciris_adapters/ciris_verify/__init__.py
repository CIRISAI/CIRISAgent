"""CIRISVerify adapter package.

This adapter integrates CIRISVerify license verification into the CIRIS agent.
The core ciris_verify bindings are provided by the 'ciris-verify' PyPI package.

Usage:
    from ciris_adapters.ciris_verify import CIRISVerifyAdapter

    adapter = CIRISVerifyAdapter(runtime, context)
    await adapter.start()
"""

# Re-export from the ciris-verify PyPI package for convenience
from ciris_verify import (  # noqa: F401
    BinaryNotFoundError,
    BinaryTamperedError,
    CapabilityCheckResult,
    CIRISVerify,
    CIRISVerifyError,
    CommunicationError,
    DisclosureSeverity,
    FileIntegrityResult,
    HardwareType,
    LicenseDetails,
    LicenseStatus,
    LicenseStatusResponse,
    LicenseTier,
    MandatoryDisclosure,
    MockCIRISVerify,
    TimeoutError,
    ValidationStatus,
    VerificationFailedError,
)

# Export adapter-specific classes
from .adapter import CIRISVerifyAdapter  # noqa: F401
from .service import CIRISVerifyService, VerificationConfig  # noqa: F401

# Alias for adapter loading code (looks for 'Adapter' class)
Adapter = CIRISVerifyAdapter

__version__ = "0.9.4"
__all__ = [
    # Adapter exports
    "Adapter",
    "CIRISVerifyAdapter",
    "CIRISVerifyService",
    "VerificationConfig",
    # Re-exports from ciris-verify package
    "CIRISVerify",
    "MockCIRISVerify",
    "LicenseStatus",
    "LicenseTier",
    "LicenseDetails",
    "MandatoryDisclosure",
    "DisclosureSeverity",
    "LicenseStatusResponse",
    "CapabilityCheckResult",
    "FileIntegrityResult",
    "HardwareType",
    "ValidationStatus",
    "CIRISVerifyError",
    "BinaryNotFoundError",
    "BinaryTamperedError",
    "VerificationFailedError",
    "TimeoutError",
    "CommunicationError",
]
