"""
Schemas for audit verification operations.

These replace all Dict[str, Any] usage in verifier.py.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.audit.hash_chain import HashChainAuditEntry


class ChainVerificationResult(BaseModel):
    """Result of hash chain verification."""

    valid: bool = Field(..., description="Whether chain is valid")
    entries_checked: int = Field(0, description="Number of entries checked")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    last_valid_entry: Optional[int] = Field(None, description="Last valid entry ID before error")


class SignatureVerificationResult(BaseModel):
    """Result of signature verification."""

    valid: bool = Field(..., description="Whether all signatures are valid")
    entries_signed: int = Field(0, description="Number of signed entries")
    entries_verified: int = Field(0, description="Number of verified signatures")
    errors: List[str] = Field(default_factory=list, description="List of signature errors")
    untrusted_keys: List[str] = Field(default_factory=list, description="List of untrusted key IDs")


class CompleteVerificationResult(BaseModel):
    """Result of complete audit chain verification."""

    valid: bool = Field(..., description="Overall validity")
    entries_verified: int = Field(0, description="Total entries verified")
    hash_chain_valid: bool = Field(..., description="Hash chain validity")
    signatures_valid: bool = Field(..., description="Signatures validity")
    verification_time_ms: int = Field(..., description="Verification time in milliseconds")
    hash_chain_errors: List[str] = Field(default_factory=list, description="Hash chain errors")
    signature_errors: List[str] = Field(default_factory=list, description="Signature errors")
    chain_summary: Optional["ChainSummary"] = Field(None, description="Chain summary information")
    summary: Optional[str] = Field(None, description="Summary message")
    error: Optional[str] = Field(None, description="Error message if verification failed")


class EntryVerificationResult(BaseModel):
    """Result of single entry verification."""

    valid: bool = Field(..., description="Whether entry is valid")
    entry_id: int = Field(..., description="Entry ID")
    hash_valid: bool = Field(..., description="Whether hash is valid")
    signature_valid: Optional[bool] = Field(None, description="Whether signature is valid if present")
    previous_hash_valid: bool = Field(..., description="Whether link to previous entry is valid")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    entry_data: Optional[HashChainAuditEntry] = Field(None, description="Entry data if requested")


class RangeVerificationResult(BaseModel):
    """Result of range verification."""

    valid: bool = Field(..., description="Whether range is valid")
    start_id: int = Field(..., description="Start entry ID")
    end_id: int = Field(..., description="End entry ID")
    entries_verified: int = Field(0, description="Number of entries verified")
    hash_chain_valid: bool = Field(..., description="Hash chain validity in range")
    signatures_valid: bool = Field(..., description="Signatures validity in range")
    errors: List[str] = Field(default_factory=list, description="List of errors in range")
    verification_time_ms: int = Field(..., description="Verification time")


class SigningKeyInfo(BaseModel):
    """Information about an audit signing key."""

    key_id: Optional[str] = Field(None, description="Key identifier")
    algorithm: Optional[str] = Field(None, description="Signing algorithm")
    key_size: Optional[int] = Field(None, description="Key size in bits")
    created_at: Optional[str] = Field(None, description="When key was created")
    revoked_at: Optional[str] = Field(None, description="When key was revoked if applicable")
    active: Optional[bool] = Field(None, description="Whether key is currently active")
    error: Optional[str] = Field(None, description="Error message if key info unavailable")


class ChainSummary(BaseModel):
    """Summary of audit chain state."""

    total_entries: int = Field(0, description="Total number of entries")
    signed_entries: int = Field(0, description="Number of signed entries")
    first_entry_id: Optional[int] = Field(None, description="First entry ID")
    last_entry_id: Optional[int] = Field(None, description="Last entry ID")
    first_entry_time: Optional[datetime] = Field(None, description="First entry timestamp")
    last_entry_time: Optional[datetime] = Field(None, description="Last entry timestamp")
    root_hash: Optional[str] = Field(None, description="Root hash if available")
    chain_intact: bool = Field(True, description="Whether chain appears intact")
    error: Optional[str] = Field(None, description="Error message if summary failed")


class VerificationReport(BaseModel):
    """Comprehensive verification report."""

    timestamp: datetime = Field(..., description="Report generation timestamp")
    verification_result: CompleteVerificationResult = Field(..., description="Verification results")
    chain_summary: ChainSummary = Field(..., description="Chain summary")
    signing_key_info: SigningKeyInfo = Field(..., description="Signing key information")
    tampering_detected: bool = Field(..., description="Whether tampering was detected")
    first_tampered_sequence: Optional[int] = Field(None, description="First tampered sequence")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")


class RootAnchorVerificationResult(BaseModel):
    """Result of root anchor verification."""

    valid: bool = Field(..., description="Whether all root anchors are valid")
    verified_count: int = Field(0, description="Number of verified anchors")
    total_count: int = Field(0, description="Total number of anchors")
    errors: List[str] = Field(default_factory=list, description="Verification errors")
    message: Optional[str] = Field(None, description="Status message")


class RefutationProof(BaseModel):
    """Proof for refuting disputed content claims."""

    timestamp: str = Field(..., description="When proof was created (ISO format)")
    stored_hash: str = Field(..., description="Hash we have stored")
    claimed_content_hash: str = Field(..., description="Hash of claimed content")
    matches_stored: bool = Field(..., description="Whether claimed content matches stored hash")
    actual_content_hash: Optional[str] = Field(None, description="Hash of actual content if available")
    actual_matches_stored: Optional[bool] = Field(None, description="Whether actual content matches stored hash")
    claimed_matches_actual: Optional[bool] = Field(None, description="Whether claimed content matches actual content")
