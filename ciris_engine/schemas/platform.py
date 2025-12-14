"""
Platform requirements and security capability schemas.

These schemas define what security/platform features an adapter or tool requires
to operate. This enables platform-bound services that require proof of possession,
device attestation, or specific hardware security features.
"""

from enum import Enum
from typing import List, Optional, Set

from pydantic import BaseModel, Field


class PlatformRequirement(str, Enum):
    """Platform security requirements for adapters and tools.

    These represent proof-of-possession and device attestation requirements
    that cannot be satisfied without specific platform capabilities.
    """

    # Mobile device attestation (proof of real device, not emulator)
    ANDROID_PLAY_INTEGRITY = "android_play_integrity"  # Google Play Integrity API
    IOS_APP_ATTEST = "ios_app_attest"  # Apple App Attest
    IOS_DEVICE_CHECK = "ios_device_check"  # Apple DeviceCheck

    # Token binding / Proof of Possession
    DPOP = "dpop"  # Demonstrating Proof of Possession (RFC 9449)
    MTLS = "mtls"  # Mutual TLS with client certificate

    # Hardware security
    TPM = "tpm"  # Trusted Platform Module
    HSM = "hsm"  # Hardware Security Module
    SECURE_ENCLAVE = "secure_enclave"  # Apple Secure Enclave / Android StrongBox
    ANDROID_KEYSTORE = "android_keystore"  # Android Keystore (hardware-backed)

    # Authentication requirements
    GOOGLE_NATIVE_AUTH = "google_native_auth"  # Native Google Sign-In (not web OAuth)
    APPLE_NATIVE_AUTH = "apple_native_auth"  # Native Apple Sign-In

    # Network requirements
    CIRIS_PROXY = "ciris_proxy"  # Requires routing through CIRIS proxy


class PlatformCapabilities(BaseModel):
    """Current platform capabilities available at runtime.

    This is populated by platform detection at startup and used to check
    if platform requirements can be satisfied.
    """

    platform: str = Field(..., description="Platform identifier (android, ios, linux, windows, macos)")
    capabilities: Set[PlatformRequirement] = Field(
        default_factory=set,
        description="Set of platform requirements this runtime can satisfy",
    )

    # Device attestation state
    play_integrity_available: bool = Field(False, description="Google Play Integrity API available")
    app_attest_available: bool = Field(False, description="Apple App Attest available")

    # Hardware security state
    hardware_keystore_available: bool = Field(False, description="Hardware-backed keystore available")
    tpm_available: bool = Field(False, description="TPM available")

    # Authentication state
    google_native_auth_available: bool = Field(False, description="Native Google Sign-In available")
    apple_native_auth_available: bool = Field(False, description="Native Apple Sign-In available")

    # Token state
    has_valid_device_token: bool = Field(False, description="Has valid device-bound token")
    token_binding_method: Optional[str] = Field(None, description="How token is bound (play_integrity, dpop, etc.)")

    def satisfies(self, requirements: List[PlatformRequirement]) -> bool:
        """Check if this platform satisfies all given requirements.

        Args:
            requirements: List of requirements to check

        Returns:
            True if all requirements are satisfied
        """
        if not requirements:
            return True
        return all(req in self.capabilities for req in requirements)

    def missing_requirements(self, requirements: List[PlatformRequirement]) -> List[PlatformRequirement]:
        """Get list of requirements that cannot be satisfied.

        Args:
            requirements: List of requirements to check

        Returns:
            List of unsatisfied requirements
        """
        return [req for req in requirements if req not in self.capabilities]


class PlatformRequirementSet(BaseModel):
    """A set of platform requirements with optional alternatives.

    Supports expressing requirements like:
    "Requires (Android Play Integrity OR iOS App Attest) AND Google Native Auth"
    """

    # All of these must be satisfied (AND)
    required: List[PlatformRequirement] = Field(
        default_factory=list,
        description="All of these requirements must be satisfied",
    )

    # At least one of these must be satisfied (OR) - for alternatives
    one_of: List[List[PlatformRequirement]] = Field(
        default_factory=list,
        description="For each inner list, at least one requirement must be satisfied",
    )

    # Human-readable explanation of why these requirements exist
    rationale: Optional[str] = Field(
        None,
        description="Why these requirements exist (shown to user if not satisfied)",
    )

    def is_satisfied_by(self, capabilities: PlatformCapabilities) -> bool:
        """Check if capabilities satisfy this requirement set.

        Args:
            capabilities: Current platform capabilities

        Returns:
            True if all requirements are satisfied
        """
        # Check all required
        if not capabilities.satisfies(self.required):
            return False

        # Check one_of groups (each group needs at least one satisfied)
        for group in self.one_of:
            if not any(req in capabilities.capabilities for req in group):
                return False

        return True


__all__ = [
    "PlatformRequirement",
    "PlatformCapabilities",
    "PlatformRequirementSet",
]
