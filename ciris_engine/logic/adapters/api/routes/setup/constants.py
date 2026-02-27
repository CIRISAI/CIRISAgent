"""Constants for CIRIS setup module.

Centralizes shared constants to avoid duplication (fixes SonarCloud issue).
"""

# Error message used when CIRISVerify is not available
# Extracted as constant to fix SonarCloud "Define a constant instead of duplicating this literal" issue
CIRISVERIFY_NOT_AVAILABLE = "CIRISVerify not available"

# Disclaimer text for Trust and Security display
VERIFY_DISCLAIMER = (
    "CIRISVerify provides cryptographic attestation of agent identity and behavior. "
    "This enables participation in the Coherence Ratchet and CIRIS Scoring. "
    "CIRISVerify is REQUIRED for CIRIS 2.0 agents."
)

# Setup mode messages
SETUP_MODE_ONLY = (
    "Setup routes are only available during first-run setup. "
    "Use /v1/auth/attestation for attestation status after setup."
)
