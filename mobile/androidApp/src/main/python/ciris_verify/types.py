"""Type definitions for CIRISVerify Python bindings.

All types use Pydantic for validation and follow CIRIS typing conventions.
"""

from enum import IntEnum, Enum
from typing import Optional, List, Set
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class LicenseStatus(IntEnum):
    """License verification status codes.

    Matches FSD-001 Section 3.2 LicenseStatus enum.
    """
    # Active licensed states (100-199)
    LICENSED_PROFESSIONAL = 100
    LICENSED_PROFESSIONAL_GRACE = 101  # Offline grace period

    # Community states (200-299)
    UNLICENSED_COMMUNITY = 200
    UNLICENSED_COMMUNITY_OFFLINE = 201

    # Restricted states (300-399)
    RESTRICTED_VERIFICATION_FAILED = 300
    RESTRICTED_SOURCES_DISAGREE = 301
    RESTRICTED_PARTIAL_AGREEMENT = 302

    # Error states (400-499)
    ERROR_BINARY_TAMPERED = 400
    ERROR_REVOKED = 401
    ERROR_EXPIRED = 402
    ERROR_HARDWARE_MISMATCH = 403
    ERROR_VERIFICATION_FAILED = 404
    ERROR_SOURCES_DISAGREE = 405

    # Lockdown (500+)
    LOCKDOWN_INTEGRITY_FAILURE = 500
    LOCKDOWN_ATTACK_DETECTED = 501

    def allows_licensed_operation(self) -> bool:
        """Check if this status allows professional licensed operations."""
        return self.value in (100, 101)

    def requires_lockdown(self) -> bool:
        """Check if this status requires immediate lockdown."""
        return self.value >= 500

    def requires_restricted(self) -> bool:
        """Check if this status forces restricted mode."""
        return 300 <= self.value < 500

    def is_community_mode(self) -> bool:
        """Check if this status is community (unlicensed) mode."""
        return 200 <= self.value < 300


class LicenseTier(IntEnum):
    """License tier levels.

    Higher tiers unlock more capabilities.
    SOFTWARE_ONLY hardware caps at COMMUNITY regardless of license.
    """
    COMMUNITY = 0           # No professional capabilities
    PROFESSIONAL_BASIC = 1  # Basic professional capabilities
    PROFESSIONAL_FULL = 2   # Full professional capabilities
    ENTERPRISE = 3          # Enterprise features


class HardwareType(str, Enum):
    """Hardware security module type.

    Determines maximum achievable license tier.
    """
    ANDROID_KEYSTORE = "android_keystore"
    ANDROID_STRONGBOX = "android_strongbox"
    IOS_SECURE_ENCLAVE = "ios_secure_enclave"
    TPM_DISCRETE = "tpm_discrete"
    TPM_FIRMWARE = "tpm_firmware"
    INTEL_SGX = "intel_sgx"
    SOFTWARE_ONLY = "software_only"

    def supports_professional_license(self) -> bool:
        """Check if this hardware supports professional licensing."""
        return self != HardwareType.SOFTWARE_ONLY

    def security_level(self) -> int:
        """Get security level (1-5, higher is better)."""
        levels = {
            HardwareType.ANDROID_STRONGBOX: 5,
            HardwareType.TPM_DISCRETE: 5,
            HardwareType.IOS_SECURE_ENCLAVE: 5,
            HardwareType.TPM_FIRMWARE: 4,
            HardwareType.INTEL_SGX: 4,
            HardwareType.ANDROID_KEYSTORE: 3,
            HardwareType.SOFTWARE_ONLY: 1,
        }
        return levels.get(self, 1)


class ValidationStatus(str, Enum):
    """Multi-source validation status."""
    ALL_SOURCES_AGREE = "all_sources_agree"
    PARTIAL_AGREEMENT = "partial_agreement"  # 2-of-3
    SOURCES_DISAGREE = "sources_disagree"    # Security alert
    NO_SOURCES_REACHABLE = "no_sources_reachable"
    VALIDATION_ERROR = "validation_error"


class DisclosureSeverity(str, Enum):
    """Severity level for mandatory disclosures."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MandatoryDisclosure(BaseModel):
    """Mandatory disclosure that MUST be shown to users.

    Per FSD-001: Agents MUST display this text when interacting with users.
    Failure to display is a violation of the CIRIS ecosystem rules.
    """
    model_config = ConfigDict(frozen=True)

    text: str = Field(..., description="Disclosure text to display")
    severity: DisclosureSeverity = Field(..., description="Severity level")
    locale: str = Field(default="en", description="Locale code")
    legal_jurisdiction: Optional[str] = Field(default=None, description="Applicable jurisdiction")


class LicenseDetails(BaseModel):
    """Detailed license information when licensed."""
    model_config = ConfigDict(frozen=True)

    license_id: str = Field(..., description="Unique license identifier")
    tier: LicenseTier = Field(..., description="License tier level")
    capabilities: Set[str] = Field(default_factory=set, description="Granted capabilities")
    prohibited_capabilities: Set[str] = Field(default_factory=set, description="Explicitly prohibited")
    issued_at: datetime = Field(..., description="License issue timestamp")
    expires_at: datetime = Field(..., description="License expiration timestamp")
    issuer: str = Field(..., description="License issuer identifier")
    holder_name: Optional[str] = Field(default=None, description="License holder name")
    holder_organization: Optional[str] = Field(default=None, description="License holder org")
    responsible_party: str = Field(default="", description="Name of the human accountable for this deployment")
    public_contact_email: str = Field(default="", description="Public-facing org contact (defaults to org owner email)")

    def has_capability(self, capability: str) -> bool:
        """Check if this license grants a specific capability."""
        if capability in self.prohibited_capabilities:
            return False
        # Wildcard matching
        for cap in self.capabilities:
            if cap == capability:
                return True
            if cap.endswith("*") and capability.startswith(cap[:-1]):
                return True
        return False


class SourceDetails(BaseModel):
    """Details about multi-source validation."""
    model_config = ConfigDict(frozen=True)

    dns_us_reachable: bool = False
    dns_eu_reachable: bool = False
    https_reachable: bool = False
    validation_status: ValidationStatus = ValidationStatus.NO_SOURCES_REACHABLE
    sources_agreeing: int = 0

    # Error details for each source (added in v0.6.6)
    # These expose the actual network error when a source fails
    dns_us_error: Optional[str] = None
    dns_us_error_category: Optional[str] = None
    dns_eu_error: Optional[str] = None
    dns_eu_error_category: Optional[str] = None
    https_error: Optional[str] = None
    https_error_category: Optional[str] = None


class AttestationData(BaseModel):
    """Hardware attestation data."""
    model_config = ConfigDict(frozen=True)

    hardware_type: HardwareType = HardwareType.SOFTWARE_ONLY
    attestation_chain: Optional[bytes] = None
    signature: Optional[bytes] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LicenseStatusResponse(BaseModel):
    """Complete license status response from CIRISVerify.

    This is the primary response type returned by get_license_status().
    """
    model_config = ConfigDict(frozen=True)

    status: LicenseStatus = Field(..., description="Overall license status")
    license: Optional[LicenseDetails] = Field(default=None, description="License details if licensed")
    mandatory_disclosure: MandatoryDisclosure = Field(..., description="Required disclosure")
    hardware_type: HardwareType = Field(default=HardwareType.SOFTWARE_ONLY)
    source_details: SourceDetails = Field(default_factory=SourceDetails)
    attestation: Optional[AttestationData] = Field(default=None)
    cached: bool = Field(default=False, description="Whether response came from cache")
    cache_age_seconds: Optional[int] = Field(default=None)
    verification_timestamp: datetime = Field(default_factory=datetime.utcnow)

    def allows_licensed_operation(self) -> bool:
        """Check if professional licensed operations are allowed."""
        return self.status.allows_licensed_operation()

    def get_prohibited_capabilities(self) -> Set[str]:
        """Get all prohibited capabilities for current status."""
        if self.license:
            return self.license.prohibited_capabilities
        # Community mode: all professional capabilities prohibited
        return {"medical:*", "legal:*", "financial:*"}

    def has_capability(self, capability: str) -> bool:
        """Check if a specific capability is allowed."""
        if not self.allows_licensed_operation():
            return False
        if self.license:
            return self.license.has_capability(capability)
        return False


class CapabilityCheckResult(BaseModel):
    """Result of checking a specific capability."""
    model_config = ConfigDict(frozen=True)

    capability: str = Field(..., description="Capability that was checked")
    allowed: bool = Field(..., description="Whether capability is allowed")
    reason: str = Field(..., description="Reason for allow/deny")
    required_tier: Optional[LicenseTier] = Field(default=None)
    current_tier: Optional[LicenseTier] = Field(default=None)
    requires_separate_module: bool = Field(default=False, description="Needs separate licensed repo")


class FileIntegrityResult(BaseModel):
    """Result of Tripwire-style agent file integrity check.

    ANY failure means the agent distribution has been tampered with
    and must be shut down immediately.
    """
    model_config = ConfigDict(frozen=True)

    integrity_valid: bool = Field(..., description="Whether all checked files passed")
    total_files: int = Field(default=0, description="Total files in manifest")
    files_checked: int = Field(default=0, description="Number of files checked")
    files_passed: int = Field(default=0, description="Files that passed hash check")
    files_failed: int = Field(default=0, description="Files with hash mismatch")
    files_missing: int = Field(default=0, description="Files missing from disk")
    files_unexpected: int = Field(default=0, description="Unexpected files not in manifest")
    failure_reason: str = Field(default="", description="Opaque failure category")


class BinaryIntegrityStatus(BaseModel):
    """Binary self-verification status (v0.6.17).

    Reports whether the running CIRISVerify binary matches its registry manifest.
    This is the "who watches the watchmen" check.
    """
    model_config = ConfigDict(frozen=True)

    status: str = Field(..., description="verified/tampered/unavailable/not_found/pending")
    version: str = Field(..., description="CIRISVerify binary version")
    target: str = Field(..., description="Target platform (e.g., x86_64-unknown-linux-gnu)")
    actual_hash: Optional[str] = Field(default=None, description="Computed hash of running binary")
    expected_hash: Optional[str] = Field(default=None, description="Expected hash from registry")
    matches: bool = Field(default=False, description="Whether hashes match")
    error: Optional[str] = Field(default=None, description="Error message if verification failed")
    verified_at: int = Field(default=0, description="Unix timestamp of verification")

    def is_verified(self) -> bool:
        """Check if binary is verified against registry."""
        return self.status == "verified" and self.matches

    def is_tampered(self) -> bool:
        """Check if binary is detected as tampered."""
        return self.status == "tampered"

    def is_available(self) -> bool:
        """Check if verification was possible (registry reachable)."""
        return self.status not in ("unavailable", "not_found", "pending")
