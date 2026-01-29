"""CIRISVerify adapter for hardware-rooted license verification.

This adapter integrates CIRISVerify with the CIRIS agent to provide:
- License status verification
- Capability enforcement based on license tier
- Mandatory disclosure management
- Hardware attestation for professional licenses

The adapter hooks into WiseBus to enforce license-based capability restrictions,
ensuring community agents cannot access professional capabilities (medical,
legal, financial) without proper licensing.
"""

from .adapter import CIRISVerifyAdapter

__all__ = ["CIRISVerifyAdapter"]
