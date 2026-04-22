"""
Schemas for audit hash chain operations.

These replace all Dict[str, Any] usage in logic/audit/hash_chain.py.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class HashChainAuditEntry(BaseModel):
    """An entry in the audit log with hash chain fields."""

    event_id: str = Field(..., description="Unique event ID")
    event_timestamp: str = Field(..., description="Event timestamp")
    event_type: str = Field(..., description="Type of event")
    originator_id: str = Field(..., description="ID of the originator")
    event_payload: str = Field("", description="Event payload data")
    sequence_number: int = Field(..., description="Sequence number in chain")
    previous_hash: str = Field(..., description="Hash of previous entry or 'genesis'")
    entry_hash: Optional[str] = Field(None, description="Hash of this entry")


class HashChainVerificationResult(BaseModel):
    """Result from verifying hash chain integrity."""

    valid: bool = Field(..., description="Whether chain is valid")
    entries_checked: int = Field(..., description="Number of entries verified")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    last_sequence: Optional[int] = Field(None, description="Last sequence number checked")
    tampering_location: Optional[int] = Field(None, description="First tampered sequence if found")


class ChainSummary(BaseModel):
    """Summary of the hash chain state."""

    total_entries: int = Field(0, description="Total number of entries")
    sequence_range: List[int] = Field(default_factory=list, description="Min and max sequence")
    current_sequence: int = Field(0, description="Current sequence number")
    current_hash: Optional[str] = Field(None, description="Current hash value")
    oldest_entry: Optional[str] = Field(None, description="Timestamp of oldest entry")
    newest_entry: Optional[str] = Field(None, description="Timestamp of newest entry")
    error: Optional[str] = Field(None, description="Error if any")


class AuditEntryResult(BaseModel):
    """Result from creating an audit entry with hash chain data (ALWAYS enabled in production)."""

    entry_id: str = Field(..., description="Unique ID of the audit entry (REQUIRED)")
    sequence_number: int = Field(..., description="Sequence number in hash chain (REQUIRED)")
    entry_hash: str = Field(..., description="Hash of this entry (REQUIRED)")
    previous_hash: Optional[str] = Field(None, description="Hash of previous entry (None for first entry)")
    signature: str = Field(..., description="Cryptographic signature (REQUIRED)")
    signing_key_id: Optional[str] = Field(None, description="ID of key used for signing")


__all__ = ["HashChainAuditEntry", "HashChainVerificationResult", "ChainSummary", "AuditEntryResult"]
