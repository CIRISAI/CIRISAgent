"""
Emergency shutdown schemas for CIRIS API v2.0.

Provides cryptographically signed emergency shutdown capability
that bypasses normal authentication for critical situations.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmergencyShutdownCommand(BaseModel):
    """
    Emergency shutdown command with cryptographic signature.

    Must be signed by a ROOT or AUTHORITY key to be valid.
    Timestamp must be within 5 minutes to prevent replay attacks.
    """

    action: Literal["emergency_shutdown"] = Field(
        "emergency_shutdown", description="Action type (always 'emergency_shutdown')"
    )
    reason: str = Field(..., description="Reason for emergency shutdown", min_length=1, max_length=500)
    timestamp: str = Field(..., description="ISO format timestamp of command creation")
    force: bool = Field(True, description="Force immediate shutdown without graceful cleanup")
    signature: str = Field(..., description="HMAC-SHA256 signature of command")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "emergency_shutdown",
                "reason": "Critical security breach detected",
                "timestamp": "2025-01-01T12:00:00Z",
                "force": True,
                "signature": "a1b2c3d4e5f6...",
            }
        }
    )


class EmergencyShutdownResponse(BaseModel):
    """Response to emergency shutdown command."""

    status: str = Field(..., description="Command status (accepted/rejected)")
    message: str = Field(..., description="Human-readable status message")
    authority: Optional[str] = Field(None, description="Authority ID who issued the command")
    timestamp: datetime = Field(..., description="When command was processed")
    shutdown_initiated: bool = Field(..., description="Whether shutdown was initiated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "accepted",
                "message": "Emergency shutdown initiated",
                "authority": "ROOT",
                "timestamp": "2025-01-01T12:00:05Z",
                "shutdown_initiated": True,
            }
        }
    )


class EmergencyStatus(BaseModel):
    """Current emergency system status."""

    emergency_system_ready: bool = Field(..., description="Whether emergency system is operational")
    trusted_authorities: int = Field(..., description="Number of trusted authority keys configured")
    last_emergency_command: Optional[datetime] = Field(None, description="Timestamp of last emergency command")
    failed_attempts_24h: int = Field(0, description="Failed emergency attempts in last 24 hours")


class EmergencySignatureResult(BaseModel):
    """Result of emergency shutdown signature verification."""

    valid: bool = Field(..., description="Whether signature is valid")
    authority_id: Optional[str] = Field(None, description="Authority ID if valid")
    reason: Optional[str] = Field(None, description="Reason for invalid signature")


class EmergencyAuditEntry(BaseModel):
    """Audit entry for emergency shutdown attempts."""

    timestamp: datetime = Field(..., description="When attempt occurred")
    success: bool = Field(..., description="Whether shutdown was initiated")
    authority_id: Optional[str] = Field(None, description="Authority ID if valid")
    reason: str = Field(..., description="Shutdown reason provided")
    failure_reason: Optional[str] = Field(None, description="Why command failed if applicable")
    source_ip: Optional[str] = Field(None, description="Source IP address")


class TrustedAuthority(BaseModel):
    """Trusted authority for emergency shutdown."""

    authority_id: str = Field(..., description="Unique authority identifier")
    public_key: str = Field(..., description="Public key for signature verification")
    role: str = Field(..., description="Role (ROOT or AUTHORITY)")
    added_at: datetime = Field(..., description="When authority was added")
    added_by: str = Field(..., description="Who added this authority")
    is_active: bool = Field(True, description="Whether authority is active")


__all__ = [
    "EmergencyShutdownCommand",
    "EmergencyShutdownResponse",
    "EmergencyStatus",
    "EmergencySignatureResult",
    "EmergencyAuditEntry",
    "TrustedAuthority",
]
