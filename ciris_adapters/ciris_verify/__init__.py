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
"""

from .client import CIRISVerify, MockCIRISVerify
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
)
from .exceptions import (
    CIRISVerifyError,
    BinaryNotFoundError,
    BinaryTamperedError,
    VerificationFailedError,
    TimeoutError,
    CommunicationError,
)

__version__ = "0.8.13"
__all__ = [
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
]
