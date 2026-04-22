"""Authority service schemas."""

from ciris_engine.schemas.services.authority.jwt import (
    JWTAlgorithm,
    JWTClaims,
    JWTHeader,
    JWTToken,
    JWTValidationResult,
)
from ciris_engine.schemas.services.authority.wise_authority import (
    ApprovalRequestContext,
    AuthenticationResult,
    DeferralResolution,
    OAuthConfig,
    PendingDeferral,
    PermissionEntry,
    TokenVerification,
    WAResource,
    WAUpdate,
)

__all__ = [
    # Wise Authority schemas
    "PermissionEntry",
    "ApprovalRequestContext",
    "AuthenticationResult",
    "WAUpdate",
    "TokenVerification",
    "PendingDeferral",
    "DeferralResolution",
    "WAResource",
    "OAuthConfig",
    # JWT schemas
    "JWTAlgorithm",
    "JWTHeader",
    "JWTClaims",
    "JWTToken",
    "JWTValidationResult",
]
