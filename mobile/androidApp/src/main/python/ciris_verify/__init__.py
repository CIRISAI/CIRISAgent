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
from .exceptions import (
    BinaryNotFoundError,
    BinaryTamperedError,
    CIRISVerifyError,
    CommunicationError,
    TimeoutError,
    VerificationFailedError,
)
from .types import (
    CapabilityCheckResult,
    DisclosureSeverity,
    FileIntegrityResult,
    HardwareType,
    LicenseDetails,
    LicenseStatus,
    LicenseStatusResponse,
    LicenseTier,
    MandatoryDisclosure,
    ValidationStatus,
)

__version__ = "0.2.0"
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
    "HardwareType",
    "ValidationStatus",
    "CIRISVerifyError",
    "BinaryNotFoundError",
    "BinaryTamperedError",
    "VerificationFailedError",
    "TimeoutError",
    "CommunicationError",
]
