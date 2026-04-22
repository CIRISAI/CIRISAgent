"""
Governance-related schemas for CIRIS.

Provides enums and models for governance operations including deferrals.
"""

from enum import Enum


class DeferralType(str, Enum):
    """Types of deferrals that can be requested."""

    ETHICAL = "ethical"
    TECHNICAL = "technical"
    POLICY = "policy"
    SAFETY = "safety"
    LEGAL = "legal"
    RESOURCE = "resource"
    AUTHORITY = "authority"
    OTHER = "other"


# Re-export the deferral classes from authority_core for convenience
from ciris_engine.schemas.services.authority_core import DeferralRequest, DeferralResponse

__all__ = ["DeferralType", "DeferralRequest", "DeferralResponse"]
