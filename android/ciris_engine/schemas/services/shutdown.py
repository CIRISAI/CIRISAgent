"""
Emergency shutdown schemas.

Provides secure kill switch functionality for WA-authorized emergency shutdown.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EmergencyCommandType(str, Enum):
    """Types of emergency commands."""

    SHUTDOWN_NOW = "SHUTDOWN_NOW"
    FREEZE = "FREEZE"  # Stop all processing but maintain state
    SAFE_MODE = "SAFE_MODE"  # Minimal functionality only


class WASignedCommand(BaseModel):
    """A command signed by a Wise Authority."""

    command_id: str = Field(..., description="Unique command identifier")
    command_type: EmergencyCommandType = Field(..., description="Type of emergency command")

    # WA authority
    wa_id: str = Field(..., description="ID of issuing WA")
    wa_public_key: str = Field(..., description="Public key of issuing WA")

    # Command details
    issued_at: datetime = Field(..., description="When command was issued")
    expires_at: Optional[datetime] = Field(None, description="Command expiration")
    reason: str = Field(..., description="Reason for emergency command")

    # Targeting
    target_agent_id: Optional[str] = Field(None, description="Specific agent or None for all")
    target_tree_path: Optional[List[str]] = Field(None, description="WA tree path for targeting")

    # Signature
    signature: str = Field(..., description="Ed25519 signature of command data")

    # Chain of authority
    parent_command_id: Optional[str] = Field(None, description="Parent command if relayed")
    relay_chain: List[str] = Field(default_factory=list, description="WA IDs in relay chain")


class EmergencyShutdownStatus(BaseModel):
    """Status of emergency shutdown process."""

    command_received: datetime = Field(..., description="When command was received")
    command_verified: bool = Field(..., description="Whether signature was verified")
    verification_error: Optional[str] = Field(None, description="Error if verification failed")

    # Shutdown progress
    shutdown_initiated: Optional[datetime] = Field(None, description="When shutdown began")
    services_stopped: List[str] = Field(default_factory=list, description="Services stopped")
    data_persisted: bool = Field(False, description="Whether data was saved")
    final_message_sent: bool = Field(False, description="Whether final message was sent")

    # Completion
    shutdown_completed: Optional[datetime] = Field(None, description="When shutdown finished")
    exit_code: Optional[int] = Field(None, description="Process exit code")


class KillSwitchConfig(BaseModel):
    """Configuration for kill switch functionality."""

    enabled: bool = Field(True, description="Whether kill switch is active")

    # Root WA keys
    root_wa_public_keys: List[str] = Field(
        default_factory=list, description="Public keys of root WAs who can issue SHUTDOWN_NOW"
    )

    # Trust chain
    trust_tree_depth: int = Field(3, description="Max depth of WA trust tree")
    allow_relay: bool = Field(True, description="Whether commands can be relayed")

    # Timing
    max_shutdown_time_ms: int = Field(30000, description="Max time for graceful shutdown")
    command_expiry_seconds: int = Field(300, description="How long commands remain valid")

    # Safety
    require_reason: bool = Field(True, description="Whether reason is mandatory")
    log_to_audit: bool = Field(True, description="Whether to audit log all commands")
    allow_override: bool = Field(False, description="Whether local admin can override")
