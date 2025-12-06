"""
Audit API response schemas - fully typed replacements for Dict[str, Any].
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class AuditContext(BaseModel):
    """Structured audit context information."""

    entity_id: Optional[str] = Field(None, description="Entity being audited")
    entity_type: Optional[str] = Field(None, description="Type of entity")
    operation: Optional[str] = Field(None, description="Operation performed")
    description: Optional[str] = Field(None, description="Human-readable description")
    request_id: Optional[str] = Field(None, description="Request ID")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    user_id: Optional[str] = Field(None, description="User who triggered action")
    ip_address: Optional[str] = Field(None, description="IP address if applicable")
    user_agent: Optional[str] = Field(None, description="User agent if applicable")
    result: Optional[str] = Field(None, description="Operation result")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[JSONDict] = Field(None, description="Additional metadata")


class EntryVerification(BaseModel):
    """Audit entry verification details."""

    signature_valid: bool = Field(..., description="Whether signature is valid")
    hash_chain_valid: bool = Field(..., description="Whether hash chain is intact")
    verified_at: datetime = Field(..., description="When verification occurred")
    verifier: str = Field("system", description="Who performed verification")
    algorithm: str = Field("sha256", description="Hash algorithm used")
    previous_hash_match: Optional[bool] = Field(None, description="Whether previous hash matches")
