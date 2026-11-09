"""Emergency shutdown: a command a seated Wise Authority signs, hybrid (100% PQC)."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EmergencyCommandType(str, Enum):
    """The one emergency command the route accepts."""

    SHUTDOWN_NOW = "SHUTDOWN_NOW"


class WASignedCommand(BaseModel):
    """An emergency command signed by the seated Wise Authority's own key.

    The signature is the authentication. Both halves are required and cover the
    RFC 8785 (JCS) canonical form of every field except the two signatures:
    Ed25519 over those bytes, ML-DSA-65 over those bytes followed by the Ed25519
    signature (CC 5.3.2.4.3.1).
    """

    command_id: str = Field(..., description="Unique command identifier")
    command_type: EmergencyCommandType = Field(..., description="Type of emergency command")
    signer_key_id: str = Field(..., description="Federation key_id of the signing Wise Authority")
    issued_at: datetime = Field(..., description="When command was issued (UTC)")
    expires_at: Optional[datetime] = Field(None, description="Command expiration")
    reason: str = Field(..., description="Reason for emergency command")
    target_agent_id: Optional[str] = Field(None, description="Specific agent, or None for this node's agent")
    signature: str = Field(..., description="Ed25519 half (base64)")
    signature_pqc: str = Field(..., description="ML-DSA-65 half (base64) over canonical || Ed25519 signature")


class EmergencyShutdownStatus(BaseModel):
    """What happened to an emergency command."""

    command_received: datetime = Field(..., description="When command was received")
    command_verified: bool = Field(..., description="Whether the hybrid signature and the signer's seat verified")
    verification_error: Optional[str] = Field(None, description="Error if verification failed")
    shutdown_initiated: Optional[datetime] = Field(None, description="When shutdown began")
    services_stopped: List[str] = Field(default_factory=list, description="Services stopped")
    data_persisted: bool = Field(False, description="Whether data was saved")
    final_message_sent: bool = Field(False, description="Whether final message was sent")
    shutdown_completed: Optional[datetime] = Field(None, description="When shutdown finished")
    exit_code: Optional[int] = Field(None, description="Process exit code")
