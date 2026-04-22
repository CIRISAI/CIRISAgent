"""
JWT-related schemas for authentication.

Provides type-safe structures for JWT tokens and claims.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

from ciris_engine.schemas.services.authority_core import JWTSubType, WARole


class JWTAlgorithm(str, Enum):
    """Supported JWT signature algorithms."""

    HS256 = "HS256"  # HMAC SHA256 (gateway tokens)
    EdDSA = "EdDSA"  # Ed25519 (WA tokens)


class JWTHeader(BaseModel):
    """JWT header information."""

    alg: JWTAlgorithm = Field(..., description="Signature algorithm")
    typ: str = Field("JWT", description="Token type")
    kid: Optional[str] = Field(None, description="Key identifier for WA tokens")

    @field_validator("typ")
    def validate_typ(cls, v: str) -> str:
        """Ensure typ is JWT."""
        if v != "JWT":
            raise ValueError("typ must be 'JWT'")
        return v


class JWTClaims(BaseModel):
    """Standard JWT claims for CIRIS tokens."""

    # Standard JWT claims
    iss: str = Field(..., description="Issuer (gateway or WA ID)")
    sub: str = Field(..., description="Subject (WA ID or channel identity)")
    aud: Union[str, List[str]] = Field(..., description="Audience (service or adapter)")
    exp: datetime = Field(..., description="Expiration time")
    iat: datetime = Field(..., description="Issued at time")
    jti: Optional[str] = Field(None, description="JWT ID for revocation")

    # CIRIS-specific claims
    sub_type: JWTSubType = Field(..., description="Subject type classification")
    role: Optional[WARole] = Field(None, description="WA role if applicable")
    name: Optional[str] = Field(None, description="Human-readable name")
    scopes: List[str] = Field(default_factory=list, description="Granted scopes/permissions")

    # Channel identity claims (for channel tokens)
    adapter_type: Optional[str] = Field(None, description="Adapter type for channel tokens")
    adapter_instance_id: Optional[str] = Field(None, description="Adapter instance ID")
    external_user_id: Optional[str] = Field(None, description="External user ID")
    external_username: Optional[str] = Field(None, description="External username")

    # OAuth claims (for OAuth tokens)
    oauth_provider: Optional[str] = Field(None, description="OAuth provider name")
    oauth_external_id: Optional[str] = Field(None, description="OAuth external ID")

    # Additional metadata
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("exp", "iat")
    def validate_timestamps(cls, v: datetime) -> datetime:
        """Ensure timestamps have timezone info."""
        if v.tzinfo is None:
            raise ValueError("Timestamps must include timezone info")
        return v

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """Check if token is expired."""
        if current_time is None:
            from datetime import timezone

            current_time = datetime.now(timezone.utc)
        return current_time >= self.exp

    def is_valid_for_audience(self, expected_audience: str) -> bool:
        """Check if token is valid for the expected audience."""
        if isinstance(self.aud, str):
            return self.aud == expected_audience
        return expected_audience in self.aud

    def has_scope(self, scope: str) -> bool:
        """Check if token has a specific scope."""
        return scope in self.scopes

    def get_wa_id(self) -> Optional[str]:
        """Extract WA ID from claims if applicable."""
        if self.sub_type in [JWTSubType.AUTHORITY, JWTSubType.USER]:
            return self.sub
        return None

    def get_channel_identity(self) -> Optional[Dict[str, str]]:
        """Extract channel identity if this is a channel token."""
        if self.sub_type == JWTSubType.ANON and self.adapter_type:
            return {
                "adapter_type": self.adapter_type,
                "adapter_instance_id": self.adapter_instance_id or "",
                "external_user_id": self.external_user_id or "",
                "external_username": self.external_username or "",
            }
        return None


class JWTToken(BaseModel):
    """Complete JWT token with header and claims."""

    header: JWTHeader = Field(..., description="JWT header")
    claims: JWTClaims = Field(..., description="JWT claims")
    signature: Optional[str] = Field(None, description="Base64url encoded signature")

    def to_string(self) -> str:
        """Convert to standard JWT string format."""
        import base64
        import json

        # Encode header
        header_json = json.dumps(self.header.model_dump(exclude_none=True), separators=(",", ":"))
        header_b64 = base64.urlsafe_b64encode(header_json.encode()).decode().rstrip("=")

        # Encode claims (convert datetime to timestamp)
        claims_dict = self.claims.model_dump(exclude_none=True)
        claims_dict["exp"] = int(self.claims.exp.timestamp())
        claims_dict["iat"] = int(self.claims.iat.timestamp())
        claims_json = json.dumps(claims_dict, separators=(",", ":"))
        claims_b64 = base64.urlsafe_b64encode(claims_json.encode()).decode().rstrip("=")

        # Combine with signature if present
        if self.signature:
            return f"{header_b64}.{claims_b64}.{self.signature}"
        return f"{header_b64}.{claims_b64}"


class JWTValidationResult(BaseModel):
    """Result of JWT validation."""

    valid: bool = Field(..., description="Whether token is valid")
    token: Optional[JWTToken] = Field(None, description="Parsed token if valid")
    error: Optional[str] = Field(None, description="Error message if invalid")
    error_type: Optional[str] = Field(None, description="Type of validation error")

    def get_wa_id(self) -> Optional[str]:
        """Get WA ID from validated token."""
        if self.valid and self.token:
            return self.token.claims.get_wa_id()
        return None

    def get_role(self) -> Optional[WARole]:
        """Get role from validated token."""
        if self.valid and self.token:
            return self.token.claims.role
        return None
